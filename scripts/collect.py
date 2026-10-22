"""Download only public HSE first-year 2026/27 course pages; retain provenance."""
import argparse, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
ROOT = Path(__file__).resolve().parents[1]
START = 'https://www.hse.ru/ba/isct/courses?course=1.1.1.4&page=1&year=2026'

def fetch(url, path, offline=False):
    if offline:
        return path.read_text(encoding='utf-8')
    r = requests.get(url, timeout=40, headers={'User-Agent': 'MIEM-course-prototype/1.0 (educational)'})
    r.raise_for_status()
    r.encoding = 'utf-8'
    path.write_text(r.text, encoding='utf-8')
    time.sleep(.3)
    return r.text

def parse(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    for e in soup(['script', 'style']): e.decompose()
    title = next((json.loads(s.string or '{}').get('name') for s in BeautifulSoup(html,'html.parser').select('script[type="application/ld+json"]') if '"Course"' in (s.string or '')), None)
    sections=[]
    for block in soup.select('.pud__section'):
        headings = block.select('.pud__title')
        if not headings: continue
        for content in block.select('.pud__content'):
            h = content.find_previous_sibling(class_='pud__title')
            if not h: h = headings[0]
            anchor = h.select_one('[id]')
            # Preserve full list items, including grading formula and module together.
            items = content.select('li.pud__list-item')
            lines = [x.get_text(' ',strip=True) for x in items] if items else [content.get_text(' ',strip=True)]
            if h.get_text(' ',strip=True) in ['Промежуточная аттестация','Interim Assessment']:
                lines=[x for x in lines if x.startswith('2026/2027')]
            text='\n'.join(x for x in lines if x)
            if text: sections.append({'section':{'Abstract':'Аннотация','Learning Objectives':'Цель освоения дисциплины','Expected Learning Outcomes':'Планируемые результаты обучения','Course Contents':'Содержание учебной дисциплины','Assessment Elements':'Элементы контроля','Interim Assessment':'Промежуточная аттестация','Recommended Core Bibliography':'Рекомендуемая основная литература','Recommended Additional Bibliography':'Рекомендуемая дополнительная литература','Authors':'Авторы'}.get(h.get_text(' ',strip=True),h.get_text(' ',strip=True)),'anchor':anchor.get('id','') if anchor else '', 'text':text})
    full=soup.get_text(' ',strip=True)
    # Metadata occurs immediately before the programme sections.
    start=full.find(title or 'NOT_FOUND', full.find('Сервис предназначен'))
    ends=[full.find(label,start) for label in ['Программа дисциплины','Course Syllabus']]
    ends=[x for x in ends if x>start]
    meta=full[start:min(ends)] if start>=0 and ends else ''
    if not title or not sections: raise ValueError('No course title or programme sections: '+url)
    if '2026/2027' not in meta or not re.search(r'1-й курс',meta):
        return None
    sections.insert(0, {'section':'О дисциплине','anchor':'','text':meta})
    return {'id':url.rsplit('/',1)[-1].split('.')[0], 'title':title, 'url':url,'year':'2026/2027','study_year':1,'sections':sections}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    raw=ROOT/'data/raw'; raw.mkdir(parents=True,exist_ok=True)
    queue=[START]; seen=set(); urls=set(); catalog=[]
    while queue:
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        html=fetch(url,raw/f'catalog-{len(seen)}.html',args.offline)
        catalog.append({'url':url,'file':f'data/raw/catalog-{len(seen)}.html','sha256':hashlib.sha256((raw/f'catalog-{len(seen)}.html').read_bytes()).hexdigest()})
        for a in BeautifulSoup(html,'html.parser').select('a[href]'):
            link=urljoin(url,a['href'])
            if re.fullmatch(r'https://www.hse.ru/ba/isct/courses/\d+\.html',link): urls.add(link)
            if '/courses/page' in link and 'course=1.1.1.4' in link and 'year=2026' in link and link not in seen: queue.append(link)
    docs=[]; errors=[]; excluded=[]
    for url in sorted(urls):
        cid=url.rsplit('/',1)[-1].split('.')[0]
        try:
            html=fetch(url,raw/f'{cid}.html',args.offline)
            doc=parse(html,url)
            if doc is None: excluded.append(url); continue
            doc.update(raw_file=f'data/raw/{cid}.html',sha256=hashlib.sha256((raw/f'{cid}.html').read_bytes()).hexdigest())
            docs.append(doc)
            (ROOT/f'data/text/{cid}.md').write_text('# '+doc['title']+'\n'+url+'\n\n'+'\n\n'.join('## '+s['section']+'\n'+s['text'] for s in doc['sections']),encoding='utf-8')
            print(doc['title'],len(doc['sections']),flush=True)
        except Exception as e: errors.append({'url':url,'error':str(e)});print('ERROR',url,str(e),flush=True)
    if not docs: raise SystemExit('No verified documents. Existing corpus left intact.')
    (ROOT/'data/courses.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2),encoding='utf-8')
    old_manifest=ROOT/'data/manifest.json'
    collected_at=json.loads(old_manifest.read_text())['collected_at'] if args.offline and old_manifest.exists() else datetime.now(timezone.utc).isoformat()
    manifest={'collected_at':collected_at,'catalogs':catalog,'discovered':len(urls),'included':len(docs),'excluded':excluded,'errors':errors}
    (ROOT/'data/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    if errors: sys.exit(1)
if __name__=='__main__': main()
