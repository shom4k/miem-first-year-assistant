import json
from pathlib import Path
import streamlit as st
from miem_assistant.engine import Assistant

st.set_page_config(page_title='Первокурсник · МИЭМ',page_icon='🎓',layout='wide')
@st.cache_resource
def load(): return Assistant()
engine=load()
manifest=json.loads((Path(__file__).parent/'data/manifest.json').read_text())
with st.sidebar:
    st.title('МИЭМ · ИВТ')
    st.caption('1 курс / 2026–2027')
    options={'Все дисциплины':None,**{d['title']:d['id'] for d in engine.docs}}
    selected=st.selectbox('Дисциплина',list(options))
    st.divider()
    st.markdown(f"**{len(engine.docs)} программ** в локальной базе")
    st.caption('Снимок: '+manifest['collected_at'][:10])
    st.caption('Работает без API-ключа. Ответы составлены из найденных выдержек. Сведения могут измениться после даты снимка.')
    st.link_button('Официальный каталог ВШЭ','https://www.hse.ru/ba/isct/courses?course=1.1.1.4&page=1&year=2026')
    if st.button('Очистить историю'):st.session_state.messages=[]
st.title('Помощник первокурсника')
st.write('Узнайте, что изучают на курсе, как считают оценку и какую литературу рекомендуют.')
with st.expander('Примеры вопросов и границы помощника'):
    st.markdown('''- Какая формула оценки по алгебре и геометрии во 2 модуле?
- Какую литературу рекомендуют по дискретной математике?
- Где изучают комплексные числа?
- С какими дисциплинами связана алгебра и геометрия?

Назовите курс или выберите его слева. Помощник ищет по программам, но не заменяет учебник: не решает задачи, не рассчитывает оценки и не знает расписание. Углубленные курсы хранятся отдельно.''')
if 'messages' not in st.session_state: st.session_state.messages=[]
def render(result):
    st.markdown(result['answer'])
    for i,s in enumerate(result['sources'],1):
        st.markdown(f"[{i}. {s['title']} — {s['section']}]({s['url']})")
        with st.expander(f'Проверить фрагмент {i}'):
            st.text(s['text'])
    if result['status'] in ['abstain','clarify']: st.caption('Ответ не подтвержден источниками или требуется уточнение.')
for message in st.session_state.messages:
    with st.chat_message(message['role']):
        if message['role']=='user': st.write(message['text'])
        else:render(message['result'])
question=st.chat_input('Вопрос о программе дисциплины…',max_chars=4000)
if question:
    st.session_state.messages.append({'role':'user','text':question})
    with st.chat_message('user'):st.write(question)
    with st.chat_message('assistant'):
        with st.spinner('Ищу в сохраненных программах…'):result=engine.answer(question,options[selected])
        render(result)
    st.session_state.messages.append({'role':'assistant','result':result})
if st.session_state.messages:
    st.download_button('Скачать историю ответов',json.dumps(st.session_state.messages,ensure_ascii=False,indent=2),'answers.json','application/json')
