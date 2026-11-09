"""Read user-defined source URLs and keywords. Tavily is optional."""
import httpx
from openpyxl import load_workbook
from .storage import add_candidate, issue
from .web_research import discover_directory, safe_url


def load_input(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    if not {'Sources','Keywords'}.issubset(set(wb.sheetnames)):
        raise ValueError('Input Excel must include Sources and Keywords sheets')
    sources=[]; keywords=[]
    for row in list(wb['Sources'].values)[1:]:
        if row and row[0] and row[1] and str(row[2] or 'Yes').strip().lower() not in ('no','0','false'):
            sources.append((str(row[0]).strip().lower(),str(row[1]).strip()))
    for row in list(wb['Keywords'].values)[1:]:
        if row and row[0] and str(row[1] or 'Yes').strip().lower() not in ('no','0','false'):
            keywords.append(str(row[0]).strip())
    wb.close()
    return sources,keywords


def tavily_search(key,query,max_results=8):
    response=httpx.post('https://api.tavily.com/search',
      json={'query':query,'search_depth':'basic','max_results':max_results,'include_answer':False},
      headers={'Authorization':f'Bearer {key}'},timeout=22)
    response.raise_for_status()
    return response.json().get('results',[])


def discovery(db,reader,input_path,tavily_key='',max_queries=3,max_directory_links=400,max_directory_pages=3):
    sources,keywords=load_input(input_path)
    count=0
    for kind,url in sources:
        if not safe_url(url):
            print(f'[SKIP] Bad URL: {url}')
            continue
        if kind=='company':
            count+=int(add_candidate(db,url,source_url=url,kind='company'))
            continue
        if kind not in ('directory','profile'):
            print(f'[SKIP] Unknown source type: {kind}');continue
        if kind=='profile':
            count+=int(add_candidate(db,url,source_url=url,kind='profile'))
            continue
        try:
            found=0; added=0
            for link,label,excerpt,ctype in discover_directory(
                    reader, url, max_directory_links, max_pages=max_directory_pages):
                is_new=int(add_candidate(db,link,label,url,excerpt,ctype))
                count+=is_new; added+=is_new; found+=1
            print(f'[DIRECTORY] {url}: {found} candidates found; {added} new')
        except Exception as exc:
            print(f'[DIRECTORY ERROR] {url}: {str(exc)[:150]}')
    if tavily_key:
        for query in keywords[:max_queries]:
            if db.execute('SELECT 1 FROM query_log WHERE query=?',(query,)).fetchone():
                continue
            try:
                results=tavily_search(tavily_key,query)
                added=0
                for item in results:
                    u=item.get('url','')
                    if safe_url(u):
                        if add_candidate(db,u,item.get('title',''),u,'','company'):
                            added+=1;count+=1
                from .storage import now
                db.execute('INSERT INTO query_log(query,searched_at,result_count) VALUES(?,?,?)',
                           (query,now(),len(results)))
                db.commit()
                print(f'[KEYWORD] {query}: {added} new candidates')
            except Exception as exc:
                print(f'[KEYWORD ERROR] {query}: {str(exc)[:170]}')
                if '429' in str(exc):
                    break
    elif keywords:
        print('[INFO] No TAVILY_API_KEY: keywords are not searched; directory links still work.')
    print(f'[DISCOVERY] Added {count} new candidates')
    return count
