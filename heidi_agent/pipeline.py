"""Run research, save checkpoints, and export from the newly created SQLite database."""
from __future__ import annotations
import traceback
from .storage import (connect,now,domain_of,add_candidate,issue,pending,mark,
                      save_company,add_fact,add_contact)
from .web_research import WebReader,Page,company_pages,find_official_website,root_url
from .discovery import discovery
from .ai_extract import call_gemini,verify_extraction,QuotaReached
from .rules_extract import grounded_rules
from .settings import config,INPUT,DATABASE,OUTPUT


def research_one(db,reader,client,model,candidate,max_pages):
    cid=candidate['id']
    url=candidate['url']
    website=root_url(url)
    seed=(candidate['source_url'],candidate['source_excerpt']) if candidate['source_excerpt'] else None
    if candidate['kind']=='profile':
        profile_url, html, text=reader.get(url)
        website=find_official_website(profile_url,html)
        seed=(profile_url,text[:3500])
        if not website:
            issue(db,cid,'NO_WEBSITE_IN_PROFILE','Public directory profile does not expose a company website')
            mark(db,cid,'needs_review','Missing company website')
            return 'needs_review'
    if not website:
        mark(db,cid,'retry','No website URL')
        return 'retry'
    # A directory may link to the same business in different entries; one domain is one lead.
    row=db.execute('SELECT id,candidate_id FROM companies WHERE website_domain=?',(domain_of(website),)).fetchone()
    if row and row['candidate_id']!=cid:
        mark(db,cid,'duplicate','Duplicate website domain of another lead')
        return 'duplicate'
    pages=company_pages(reader,website,max_pages=max_pages,seed_profile=seed)
    # Quote verification uses full fetched page text, not model hallucination.
    result=call_gemini(client,model,pages)
    facts,contacts,rejected=verify_extraction(result,pages)
    # Deterministic fallback for explicitly published directory/site statements.
    rule_facts,rule_contacts=grounded_rules(pages)
    known_fields={field for field,value,quote,source in facts}
    for field,value,quote,source in rule_facts:
        if field not in known_fields:
            facts.append((field,value,quote,source))
            known_fields.add(field)
    known_contacts={(name.casefold(),email.casefold()) for name,role,email,phone,link,quote,source in contacts}
    for item in rule_contacts:
        key=(item[0].casefold(),item[2].casefold())
        if key not in known_contacts:
            contacts.append(item)
            known_contacts.add(key)
    name=next((v for f,v,q,u in facts if f=='company_name'),candidate['name_hint'])
    if not name.strip() or len(name)>180:
        name=domain_of(website)
    co_id=save_company(db,cid,name,website)
    for field,value,quote,source in facts:
        add_fact(db,co_id,field,value,quote,source)
    for name,role,email,phone,linkedin,quote,source in contacts:
        add_contact(db,co_id,name,role,email,phone,linkedin,quote,source)
    db.commit()
    for code,detail in rejected[:20]:
        issue(db,cid,code,detail)
    if not facts and not contacts:
        issue(db,cid,'NO_VERIFIED_FACTS','No AI-extracted facts could be verified against source text')
        mark(db,cid,'retry','Extraction returned no verified facts')
        return 'retry'
    mark(db,cid,'researched')
    return 'researched'


def run(limit=10,max_queries=3,max_pages=4,max_directory_links=400):
    opts=config()
    if not opts['gemini_key']:
        raise RuntimeError('Add GEMINI_API_KEY in .env before running research. The agent does not charge automatically.')
    from google import genai
    db=connect(DATABASE)
    reader=WebReader(opts['http_timeout'],opts['crawl_delay'])
    print('[DATABASE] New/previous runs of THIS clean project only:',DATABASE)
    try:
        discovery(db,reader,INPUT,opts['tavily_key'],max_queries,max_directory_links)
        jobs=pending(db,limit)
        print(f'[RESEARCH] Up to {len(jobs)} candidates this run. Gemini model: {opts["model"]}')
        with genai.Client(api_key=opts['gemini_key']) as client:
            count=0
            for i,c in enumerate(jobs,1):
                if count>=opts['max_gemini_calls']:
                    print('[BUDGET] Per-run Gemini call budget reached; run again later.')
                    break
                # Company research may fail before an API call; conservative budget includes attempts.
                count+=1
                print(f'  [{i}/{len(jobs)}] #{c["id"]} {c["url"]}',flush=True)
                try:
                    status=research_one(db,reader,client,opts['model'],c,max_pages)
                    print('    =>',status,flush=True)
                except QuotaReached as exc:
                    issue(db,c['id'],'GEMINI_QUOTA',str(exc)[:240])
                    print('[STOP] Gemini quota/rate limit encountered. No additional calls will be made.')
                    break
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as exc:
                    msg=f'{type(exc).__name__}: {str(exc)[:250]}'
                    issue(db,c['id'],'RESEARCH_ERROR',msg)
                    mark(db,c['id'],'retry',msg)
                    print('    => retry:',msg,flush=True)
        return db
    finally:
        reader.close()


def export_from_db(db):
    from .export_excel import export_excel
    from .method_doc import create_methodology_doc
    OUTPUT.mkdir(parents=True,exist_ok=True)
    xlsx=OUTPUT/'Heidi_Berlin_Leads.xlsx'
    docx=OUTPUT/'Heidi_Research_Methodology.docx'
    export_excel(db,xlsx)
    create_methodology_doc(db,docx)
    print(f'[OUTPUT] Excel: {xlsx}')
    print(f'[OUTPUT] Research approach document: {docx}')
    return xlsx,docx
