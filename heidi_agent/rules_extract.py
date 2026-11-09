"""Conservative non-AI extraction for explicit German business facts in page text.

Each accepted result includes a substring of public page text. These rules are
intentionally narrow; an unknown is preferable to an incorrect claim.
"""
import re
from .ai_extract import norm

BOOL_PATTERNS={
    'weg_management': r'\b(?:WEG[ -]?Verwaltung|Wohnungseigentumsverwaltung|Verwaltung von Wohnungseigentum)\b',
    'residential_management': r'\b(?:Mietverwaltung|Wohnungsverwaltung|Wohnimmobilienverwaltung)\b',
    'commercial_management': r'\b(?:Gewerbeimmobilienverwaltung|Gewerbeverwaltung)\b',
    'heating_billing_relevance': r'\b(?:Heizkostenabrechnung|Verbrauchsabrechnung|Heizkostenverteiler|Heizkostenmanagement)\b',
    'digital_operations_fit': r'\b(?:digitales Kundenportal|Online[ -]?Portal|Eigentümerportal|Mieterportal)\b',
}

NAME_RE=re.compile(r'\b((?:[\wÄÖÜäöüß&.,–-]+\s+){1,6}(?:GmbH|AG|UG|e\.K\.))\b',re.I)
EMAIL_RE=re.compile(r'(?<![\w.])([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})(?![\w.])')
GENERIC_EMAILS={'info','office','mail','kontakt','team','verwaltung','service','hello','support','post','anfrage'}
PERSON_RE=re.compile(r'\b([A-ZÄÖÜ][a-zäöüß][a-zA-ZäöüßÄÖÜ-]{1,32}\s+[A-ZÄÖÜ][a-zäöüß][a-zA-ZäöüßÄÖÜ-]{1,32})\s*$')


def excerpt(text,match,margin=36):
    start=max(0,match.start()-margin)
    end=min(len(text),match.end()+margin)
    # Never alter the quote; it must be copied directly from this text.
    return text[start:end]


def grounded_rules(pages):
    facts=[];contacts=[]
    fields_seen=set()
    emails_seen=set()
    for page in pages:
        s=page.text
        if not s:
            continue
        for field,pattern in BOOL_PATTERNS.items():
            if field in fields_seen:
                continue
            match=re.search(pattern,s,re.I)
            if match:
                quote=excerpt(s,match)
                facts.append((field,'Yes',quote,page.url))
                fields_seen.add(field)
        # Berlin presence only on address / explicit operating-place statement.
        if 'berlin_presence' not in fields_seen:
            m=re.search(r'\b1\d{4}\s+Berlin\b|\b(?:Sitz in|Standort in|Standort|Büro in)\s+Berlin\b',s,re.I)
            if m:
                facts.append(('berlin_presence','Yes',excerpt(s,m),page.url))
                fields_seen.add('berlin_presence')
        if 'company_name' not in fields_seen:
            m=NAME_RE.search(s[:2100])
            if m:
                name=m.group(1).strip()
                # Avoid capturing generic website marketing phrases as company names.
                if len(name)<125:
                    facts.append(('company_name',name,m.group(1),page.url))
                    fields_seen.add('company_name')
        # Portfolio count only if directly tied to the company and explicitly managed.
        if 'portfolio_units' not in fields_seen:
            m=re.search(r'\b(?:verwalten|verwalteten|betreuen|betreuten)\s+(?:wir\s+)?(?:aktuell\s+)?(?:rund\s+)?(\d[\d.\s]*)\s*(?:Wohnungen|Wohneinheiten|Einheiten)\b',s,re.I)
            if m and not re.search(r'\b(?:über|mehr als|mindestens|bis zu)\b',s[max(0,m.start()-20):m.start()],re.I):
                number=re.sub(r'\D','',m.group(1))
                if number and 1<=int(number)<=10_000_000:
                    facts.append(('portfolio_units',number,excerpt(s,m),page.url))
                    fields_seen.add('portfolio_units')
        # Public generic email: not a named decision maker.
        for m in EMAIL_RE.finditer(s):
            email=m.group(1)
            if email.lower() in emails_seen:
                continue
            emails_seen.add(email.lower())
            if email.split('@')[0].lower() in GENERIC_EMAILS and 'general_email' not in fields_seen:
                facts.append(('general_email',email,excerpt(s,m),page.url))
                fields_seen.add('general_email')
                continue
            preceding=s[max(0,m.start()-90):m.start()].strip()
            name_match=PERSON_RE.search(preceding)
            if not name_match:
                continue
            name=name_match.group(1)
            if any(w in name.lower().split() for w in ('verwaltung','gmbh','adresse','telefon','internet','kontakt','büro','homepage')):
                continue
            source_quote=s[max(0,m.start()-len(name)-1):m.end()]
            if norm(name) not in norm(source_quote):
                source_quote=excerpt(s,m,margin=65)
            contacts.append((name,'',email,'','',source_quote,page.url))
    return facts,contacts
