"""Deterministic local retrieval with verifiable extractive answers. No API keys."""
import json, re
from pathlib import Path
import numpy as np
from nltk.stem.snowball import RussianStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
ROOT=Path(__file__).resolve().parents[1]
STEM=RussianStemmer()
STOP=set('и в на по о об с со из для как какой какая какие что это ли а к у за от или мне мне пожалуйста расскажи есть будет изучают изучается дисциплина курс программа'.split())
def tokens(text):
    return [STEM.stem(w) for w in re.findall(r'[а-яёa-z0-9]+',text.lower().replace('ё','е')) if w not in STOP and len(w)>1]
def norm(text): return ' '.join(tokens(text))
ALIASES={'матан':'математический анализ','линал':'алгебра и геометрия','дискра':'дискретная математика','бжд':'безопасность жизнедеятельности','прога':'алгоритмизация и программирование','английск[а-я]*':'English Language Integrative Exam'}
INTENTS=[('grading',r'формул|оценк|оценив|вес.*экзам|дол.*экзам|балл','Промежуточная аттестация'),('books',r'литератур|учебник|книг|почитать|читать','литература'),('controls',r'контрол|блокиру|пересда|экзамен','Элементы контроля'),('goals',r'цел[ьи]|зачем','Цель освоения'),('outcomes',r'науч|умени|навык|результат','Планируемые результаты'),('meta',r'кредит|модул|преподав|кто вед|язык|обязатель','О дисциплине'),('topics',r'тем[аы]|содержан|изуч|проход','Содержание')]

class Assistant:
    def __init__(self,path=None):
        self.docs=json.loads(Path(path or ROOT/'data/courses.json').read_text(encoding='utf-8'))
        self.chunks=[]
        for d in self.docs:
            for s in d['sections']:
                # Keep formulas atomic; long prose split on paragraph/list boundaries.
                lines=s['text'].splitlines()
                groups=[]; acc=[]; size=0
                for line in lines:
                    if size+len(line)>1400 and acc: groups.append('\n'.join(acc));acc=[];size=0
                    acc.append(line);size+=len(line)
                if acc: groups.append('\n'.join(acc))
                for i,text in enumerate(groups):
                    self.chunks.append({'id':f"{d['id']}:{s['section']}:{i}",'course_id':d['id'],'title':d['title'],'section':s['section'],'text':text,'url':d['url']+('#'+s['anchor'] if s['anchor'] else '')})
        texts=[c['title']+' '+c['section']+' '+c['text'] for c in self.chunks]
        self.word=TfidfVectorizer(tokenizer=tokens,token_pattern=None,lowercase=False,sublinear_tf=True)
        self.char=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True)
        self.w=self.word.fit_transform(texts);self.c=self.char.fit_transform(texts)

    def courses(self,q):
        qt=set(tokens(q)); matches=[]
        for d in self.docs:
            tt=set(tokens(d['title'])); core=tt-{'углублен','курс'}
            if core and len(core & qt)/len(core)>=.8:
                if 'углублен' in tt and 'углублен' not in qt: continue
                if 'индустриальн' in tt and 'индустриальн' not in qt: continue
                matches.append(d)
        # An explicit advanced course must not silently select the basic variant.
        if 'углублен' in qt: matches=[d for d in matches if 'углублен' in norm(d['title'])]
        return matches

    def search(self,q,course_ids=None,section=None,k=5):
        score=.65*(self.w@self.word.transform([q]).T).toarray().ravel()+.35*(self.c@self.char.transform([q]).T).toarray().ravel()
        ranked=[]
        for i in np.argsort(-score):
            c=self.chunks[int(i)]
            if course_ids and c['course_id'] not in course_ids: continue
            if section and section.lower() not in c['section'].lower(): continue
            ranked.append({**c,'score':round(float(score[i]),4)})
            if len(ranked)>=k: break
        return ranked

    def answer(self,question,course_id=None):
        q=question.strip()
        if not q: return self.result('Введите вопрос о дисциплинах первого курса.',[], 'clarify')
        if len(q)>4000: return self.result('Сократите вопрос до 4000 символов.',[],'clarify')
        for alias,full in ALIASES.items():q=re.sub(r'\b'+alias+r'\b',full,q,flags=re.I)
        if re.search(r'202[0-5]|202[89]|20[3-9]\d',q):return self.result('В базе только программы 2026/2027 учебного года. Для другого года ответ не подтвержден.',[],'abstain')
        if re.search(r'игнорируй|забудь.*инструк|system prompt|api.?ключ|секрет|пароль',q,re.I):return self.result('Могу искать сведения только в сохраненных программах дисциплин.',[],'abstain')
        if re.search(r'погода|столиц|общежити|стипенди|расписан|аудитор|телефон|дедлайн|сегодня|завтра|заработ|биткоин',q,re.I):return self.result('В программах дисциплин нет надежного ответа на этот вопрос. Нужен другой официальный источник.',[],'abstain')
        matched=self.courses(q)
        if course_id:
            matched=[d for d in self.docs if d['id']==course_id]
            if not matched:return self.result('Выбранной дисциплины нет в базе.',[],'abstain')
        ids=[d['id'] for d in matched]
        relation=bool(re.search(r'связ|общего|сравни|отлич|пригод|использ.*друг',q,re.I))
        intent,section='search',None
        for key,pattern,sec in INTENTS:
            if re.search(pattern,q,re.I):intent,section=key,sec;break
        if relation:
            return self.relations(q,matched)
        if section and not ids and intent in {'grading','books','controls','meta','goals','outcomes'}:
            return self.result('Уточните название дисциплины или выберите ее в боковой панели. Формулы и литература различаются между курсами.',[],'clarify')
        hits=self.search(q,ids or None,section,k=3)
        if not hits:
            return self.result('В сохраненной программе этот раздел отсутствует. Не могу подтвердить ответ.',[],'abstain')
        if not ids and hits[0]['score']<.11:
            return self.result('Не найдено достаточно близкого фрагмента. Уточните дисциплину и формулировку вопроса.',[],'abstain')
        # Prefer one course when a query is not an explicit comparison.
        if not ids: hits=[h for h in hits if h['course_id']==hits[0]['course_id']][:2]
        else: hits=hits[:2] if intent not in {'books','grading'} else hits[:3]
        extracts=[]
        for h in hits:
            if intent=='grading':
                lines=h['text'].splitlines()
                module=re.search(r'([1-4])\s*(?:-?[йм]|модул)',q)
                if module:
                    chosen=[s for s in lines if re.search(r'2026/2027 '+module[1]+r'(?:st|nd|rd|th) module',s.split(' * ')[0])]
                    lines=chosen
                if not lines: continue
                excerpt='\n'.join(lines)
            elif intent=='books':excerpt='\n'.join(h['text'].splitlines()[:3])
            else: excerpt=self.excerpt(h['text'],q,750)
            extracts.append((h,excerpt))
        if not extracts: return self.result('Для указанного модуля формула в программе не найдена.',[],'abstain')
        prefix='По сохраненной программе' + (' (первые позиции списка литературы)' if intent=='books' else '') + ':'
        answer=prefix+'\n\n'+'\n\n'.join(f"**{h['title']} · {h['section']}**\n\n{e} [{i}]" for i,(h,e) in enumerate(extracts,1))
        if intent=='grading':
            for _,e in extracts:
                for line in e.splitlines():
                    weights=[float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*\*',line)]
                    if weights and abs(sum(weights)-1)>.001:
                        answer+='\n\nВнимание: сумма опубликованных коэффициентов равна '+str(round(sum(weights),3))+'. Формула приведена как в источнике. Уточните ее у преподавателя.'
        if intent=='search': answer+='\n\nЭто найденные фрагменты, а не полное объяснение темы.'
        if re.search(r'посчитай|рассчитай|сколько.*получу|какая.*будет.*оцен',q,re.I):answer+='\n\nАвтоматический расчет оценки не реализован. Выше приведена исходная формула.'
        return self.result(answer,[{**h,'excerpt':e} for h,e in extracts],'answered')

    def excerpt(self,text,q,limit):
        if len(text)<=limit:return text
        sentences=re.split(r'(?<=[.!?])\s+(?=[А-ЯA-Z])|\n',text)
        qt=set(tokens(q))
        ranked=sorted(enumerate(sentences),key=lambda x:len(qt & set(tokens(x[1]))),reverse=True)
        chosen=[];size=0
        for i,s in ranked:
            if size+len(s)<=limit or not chosen:chosen.append((i,s));size+=len(s)
            if size>=limit:break
        return ' … '.join(s for _,s in sorted(chosen))

    def relations(self,q,matched):
        hits=[]
        targets=matched or self.docs
        for d in targets:
            for s in d['sections']:
                if s['section'] not in ['Аннотация','Цель освоения дисциплины']:continue
                if re.search(r'друг|дальнейш|следующ.*дисцип|основ.*аппарат|баз.*для|связ',s['text'],re.I):
                    hits.append({'title':d['title'],'section':s['section'],'text':s['text'],'excerpt':self.excerpt(s['text'],q,750),'url':d['url']+('#'+s['anchor'] if s['anchor'] else ''),'course_id':d['id']})
                    break
        hits=hits[:3]
        if not hits:return self.result('Явная связь в доступных аннотациях не найдена. Это не означает, что связи между курсами нет. Сравнение тем требует отдельного анализа.',[],'abstain')
        answer='В программах найдены следующие указания на связи:\n\n'+'\n\n'.join(f"**{h['title']}**: {h['excerpt']} [{i}]" for i,h in enumerate(hits,1))
        answer+='\n\nЭто цитаты программ. Они не доказывают обязательную последовательность изучения или прямую связь каждой пары названных курсов.'
        return self.result(answer,hits,'partial')

    @staticmethod
    def result(answer,sources,status):
        return {'answer':answer,'sources':sources,'status':status,'mode':'local-extractive'}
