"""Fresh, local SQLite database. Never imports old files."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url: str):
    url = (url or '').strip()
    if not url:
        return ''
    if not url.startswith(('https://','http://')):
        url = 'https://' + url
    p = urlsplit(url)
    if not p.hostname:
        return ''
    host = p.hostname.lower().removeprefix('www.')
    return f'https://{host}{p.path.rstrip("/") or "/"}'


def domain_of(url: str):
    try:
        return (urlsplit(normalize_url(url)).hostname or '').removeprefix('www.')
    except Exception:
        return ''


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,
            name_hint TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
            source_excerpt TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'company',
            status TEXT NOT NULL DEFAULT 'new', attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '', discovered_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL UNIQUE REFERENCES candidates(id),
            name TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
            website_domain TEXT NOT NULL DEFAULT '', last_researched TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
            field TEXT NOT NULL, value TEXT NOT NULL, quote TEXT NOT NULL,
            source_url TEXT NOT NULL, verified_at TEXT NOT NULL,
            UNIQUE(company_id, field, value, source_url)
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '', linkedin_url TEXT NOT NULL DEFAULT '',
            quote TEXT NOT NULL, source_url TEXT NOT NULL, verified_at TEXT NOT NULL,
            UNIQUE(company_id, name, email, source_url)
        );
        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates(id),
            issue_code TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(candidate_id, issue_code, detail)
        );
        CREATE TABLE IF NOT EXISTS query_log (
            query TEXT PRIMARY KEY, searched_at TEXT NOT NULL, result_count INTEGER NOT NULL
        );
    ''')
    db.commit()
    return db


def add_candidate(db, url, name_hint='', source_url='', source_excerpt='', kind='company'):
    url = normalize_url(url)
    if not url:
        return False
    # Merge across directory sources by canonical full URL; domain dedupe at research stage.
    row = db.execute('SELECT id FROM candidates WHERE url=?', (url,)).fetchone()
    if row:
        return False
    db.execute('''INSERT INTO candidates (url,name_hint,source_url,source_excerpt,kind,discovered_at)
        VALUES(?,?,?,?,?,?)''', (url, name_hint[:200], source_url[:1500],
        source_excerpt[:1800],kind,now()))
    db.commit()
    return True


def issue(db, candidate_id, code, detail):
    db.execute('INSERT OR IGNORE INTO issues(candidate_id,issue_code,detail,created_at) VALUES(?,?,?,?)',
               (candidate_id,code,detail[:1200],now()))
    db.commit()


def pending(db, limit):
    return db.execute("""SELECT * FROM candidates WHERE status IN ('new','retry')
                 AND attempts < 3 ORDER BY CASE WHEN kind='company' THEN 0 ELSE 1 END, id LIMIT ?""",
                 (limit,)).fetchall()


def mark(db,cid,status,error=''):
    db.execute('UPDATE candidates SET status=?,last_error=?,attempts=attempts+1 WHERE id=?',
               (status,error[:1200],cid))
    db.commit()


def save_company(db, candidate_id, name, website):
    domain=domain_of(website)
    db.execute('''INSERT INTO companies(candidate_id,name,website,website_domain,last_researched)
        VALUES(?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET name=excluded.name,
        website=excluded.website,website_domain=excluded.website_domain,
        last_researched=excluded.last_researched''', (candidate_id,name[:220],website[:1500],domain,now()))
    db.commit()
    return db.execute('SELECT id FROM companies WHERE candidate_id=?',(candidate_id,)).fetchone()['id']


def add_fact(db, company_id, field, value, quote, url):
    db.execute('''INSERT OR IGNORE INTO facts(company_id,field,value,quote,source_url,verified_at)
        VALUES(?,?,?,?,?,?)''', (company_id,field,value[:400],quote[:550],url[:1500],now()))


def add_contact(db, company_id, name, role, email, phone, linkedin, quote, url):
    db.execute('''INSERT OR IGNORE INTO contacts
        (company_id,name,role,email,phone,linkedin_url,quote,source_url,verified_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', (company_id,name[:180],role[:150],email[:240],phone[:80],
                                        linkedin[:600],quote[:550],url[:1500],now()))
