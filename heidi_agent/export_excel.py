"""Export Heidi's existing SQLite research to a polished, reproducible Excel workbook.

This module is a drop-in replacement for heidi_agent/export_excel.py.
It does not run discovery, Gemini, or change the database.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .scoring import best_facts, score_company


NAVY = '16253F'
BLUE = '244A73'
TEAL = '167E83'
WHITE = 'FFFFFF'
PALE = 'E8F3F5'
GREEN = 'DFF1E7'
AMBER = 'FFF0C5'
TEXT = '253449'
LIGHT = 'F5F8FB'

M_HEADERS = [
    'Rank', 'Company ID', 'Company Name', 'Website', 'Berlin Presence',
    'Address', 'City', 'Residential Management', 'WEG Management',
    'Commercial Management', 'Managed Apartments / Units',
    'Heating / Billing Relevance', 'Portfolio Complexity',
    'Digital / Operational Fit', 'Lead Score / 100', 'Priority',
    'Qualification', 'Data Completeness %', 'Best Contact Name', 'Role',
    'General Email', 'Professional Email', 'Phone', 'LinkedIn',
    'Research Status', 'Original Source', 'Last Research', 'Review Notes',
]
CONTACT_HEADERS = [
    'Company Name', 'Company ID', 'Lead Score', 'Priority', 'Contact Name',
    'Role', 'General Email', 'Professional Email', 'Phone', 'LinkedIn',
    'Source URL', 'Evidence Quote',
]
EVIDENCE_HEADERS = [
    'Company Name', 'Company ID', 'Field', 'Verified Value', 'Source URL',
    'Exact Supporting Quote', 'Verified UTC',
]
SCORE_HEADERS = [
    'Company Name', 'Company ID', 'Qualification', 'Lead Score', 'KPI',
    'Points', 'Maximum', 'Reason', 'Evidence URL',
]
ISSUES_HEADERS = [
    'Company Name', 'Candidate ID', 'Research Status', 'Issue Code',
    'Detail', 'Logged UTC',
]
CANDIDATE_HEADERS = [
    'Candidate ID', 'Name Hint', 'Candidate URL', 'Source URL',
    'Type', 'Status', 'Attempts', 'Last Error',
]

# Shared/team inboxes are company contacts, not person-specific emails.
GENERAL_PREFIXES = {
    'info', 'kontakt', 'contact', 'office', 'mail', 'service',
    'verwaltung', 'team', 'hello', 'support', 'post', 'anfrage',
    'empfang', 'sekretariat', 'rezeption', 'buchhaltung', 'billing',
    'rechnung', 'admin', 'zentrale', 'hv', 'kundenservice',
    'abrechnung', 'mietverwaltung', 'weg', 'presse', 'jobs',
    'bewerbung', 'personal', 'recruiting', 'vertrieb', 'sales',
    'noreply', 'no-reply', 'datenschutz', 'marketing', 'vermietung',
}
INVALID_NAME_TERMS = {
    'schadensmeldung', 'kontakt', 'contact', 'service', 'verwaltung',
    'team', 'impressum', 'anfrage', 'datenschutz', 'kundenservice',
    'unternehmen', 'hausverwaltung', 'gesellschaft', 'gmbh',
}
EMAIL_RE = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', re.I)
NUMERIC_RE = re.compile(r'-?\d+(?:[.,]\d+)?%?')


def emails_in(value):
    """Return unique syntactically plausible emails found in one field."""
    seen = set()
    result = []
    for match in EMAIL_RE.findall(str(value or '')):
        email = match.strip().strip('.,;:<>[]()').lower()
        if email not in seen:
            seen.add(email)
            result.append(email)
    return result


def is_general_email(email):
    local = email.split('@', 1)[0].lower()
    prefix = re.split(r'[._+\-]', local, maxsplit=1)[0]
    return prefix in GENERAL_PREFIXES


def plausible_person_name(name):
    parts = re.sub(r'\s+', ' ', str(name or '')).strip().split(' ')
    if not 2 <= len(parts) <= 6:
        return False
    if any(char.isdigit() for char in ' '.join(parts)):
        return False
    words = {re.sub(r'[^a-zäöüß]', '', word.casefold()) for word in parts}
    if words & INVALID_NAME_TERMS:
        return False
    return all(len(word) > 1 for word in parts)


def classify_contact_email(person):
    """Return (person-specific professional email, general company email).

    A non-generic address is counted as professional only when the same source
    excerpt supports the named person AND the exact email. Other addresses
    stay in the database, but are not presented as verified direct contacts.
    """
    addresses = emails_in(person['email'])
    if not addresses:
        return '', ''

    general = next((e for e in addresses if is_general_email(e)), '')
    name = re.sub(r'\s+', ' ', str(person['name'] or '')).strip()
    quote = re.sub(r'\s+', ' ', str(person['quote'] or '')).casefold()
    source = str(person['source_url'] or '').strip()
    professional = ''

    if plausible_person_name(name) and source:
        for email in addresses:
            if not is_general_email(email) and name.casefold() in quote and email in quote:
                professional = email
                break

    return professional, general


def find_company_emails(people, facts):
    """One consistent classification for Master Companies and Dashboard."""
    professional = ''
    general = ''
    direct_person = None
    for person in people:
        p, g = classify_contact_email(person)
        if p and not professional:
            professional = p
            direct_person = person
        if g and not general:
            general = g

    # Some extracts contain the general mailbox as a company fact instead of
    # a contact row. Only email-named fact fields and generic inboxes qualify.
    if not general:
        for key, fact in facts.items():
            if 'email' not in key.casefold() and key.casefold() not in ('e_mail', 'e-mail'):
                continue
            for email in emails_in(fact.get('value') if isinstance(fact, dict) else ''):
                if is_general_email(email):
                    general = email
                    break
            if general:
                break
    return professional, general, direct_person


def prepare_sheet(wb, name, headers, widths=None):
    sh = wb.create_sheet(name)
    end = get_column_letter(len(headers))
    sh.merge_cells(f'A1:{end}1')
    sh['A1'] = 'HEIDI SYSTEMS  /  BERLIN LEAD RESEARCH'
    sh['A1'].font = Font(name='Aptos Display', size=16, bold=True, color=WHITE)
    sh['A1'].fill = PatternFill('solid', fgColor=NAVY)
    sh['A1'].alignment = Alignment(vertical='center')
    sh.row_dimensions[1].height = 32

    for col, value in enumerate(headers, 1):
        cell = sh.cell(4, col, value)
        cell.font = Font(name='Aptos', size=10, bold=True, color=WHITE)
        cell.fill = PatternFill('solid', fgColor=BLUE)
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    sh.row_dimensions[4].height = 35
    sh.freeze_panes = 'D5' if name == 'Master Companies' else 'B5'
    for col, header in enumerate(headers, 1):
        sh.column_dimensions[get_column_letter(col)].width = (
            widths or {}
        ).get(header, 18 if len(header) < 14 else 23)
    sh.sheet_view.showGridLines = False
    return sh


def write_rows(sh, rows, url_columns=(), score_column=None):
    for idx, row in enumerate(rows, 5):
        sh.row_dimensions[idx].height = 23
        for col, value in enumerate(row, 1):
            cell = sh.cell(idx, col, value)
            cell.font = Font(name='Aptos', size=10, color=TEXT)
            numeric = (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            ) or bool(NUMERIC_RE.fullmatch(str(value or '').strip()))
            cell.alignment = Alignment(
                vertical='center',
                horizontal='center' if numeric else 'left',
                wrap_text=False,
            )
            if idx % 2 == 0:
                cell.fill = PatternFill('solid', fgColor=LIGHT)
            if col in url_columns and isinstance(value, str) and value.startswith(('http://', 'https://')):
                cell.hyperlink = value
                cell.font = Font(name='Aptos', size=10, color='1471A8', underline='single')
            if score_column == col and isinstance(value, (float, int)):
                cell.font = Font(name='Aptos', size=10, bold=True, color=TEAL)
    n = max(4, len(rows) + 4)
    sh.auto_filter.ref = f'A4:{get_column_letter(sh.max_column)}{n}'
    if score_column and rows:
        letter = get_column_letter(score_column)
        sh.conditional_formatting.add(
            f'{letter}5:{letter}{n}',
            CellIsRule(operator='greaterThanOrEqual', formula=['75'],
                       fill=PatternFill('solid', fgColor=GREEN)),
        )
        sh.conditional_formatting.add(
            f'{letter}5:{letter}{n}',
            CellIsRule(operator='between', formula=['50', '74'],
                       fill=PatternFill('solid', fgColor=AMBER)),
        )


def load_records(db):
    cands = db.execute('''
        SELECT c.*, p.id AS company_id, p.name AS company_name,
               p.website, p.last_researched
        FROM candidates c
        LEFT JOIN companies p ON p.candidate_id = c.id
    ''').fetchall()
    facts, contacts = {}, {}
    for rec in db.execute('SELECT * FROM facts ORDER BY id DESC').fetchall():
        facts.setdefault(rec['company_id'], []).append(rec)
    for rec in db.execute('SELECT * FROM contacts ORDER BY id DESC').fetchall():
        contacts.setdefault(rec['company_id'], []).append(rec)

    all_items = []
    for c in cands:
        f = best_facts(facts.get(c['company_id'], []))
        scoring = score_company(f)
        people = contacts.get(c['company_id'], [])
        professional, general, direct_person = find_company_emails(people, f)

        # Prioritize the person associated with an evidence-backed direct email.
        # Otherwise show a plausible named person, not a generic mailbox name.
        if direct_person is not None:
            top = direct_person
        else:
            top = next(
                (p for p in people if plausible_person_name(p['name']) and (p['role'] or p['linkedin_url'])),
                None,
            )

        name = (f.get('company_name', {}).get('value') or c['company_name']
                or c['name_hint'] or '(Not yet identified)')
        website = c['website'] or c['url']

        def fval(field):
            value = f.get(field, {}).get('value', 'Unknown')
            return str(value) if value is not None and str(value).strip() else 'Unknown'

        portfolio_text = fval('portfolio_units')
        portfolio = int(portfolio_text) if portfolio_text.isdigit() else 'Unknown'
        notes = []
        if c['status'] not in ('researched', 'duplicate'):
            notes.append('Research incomplete')
        if scoring['qualification'] != 'Qualified (provisional)':
            notes.append(scoring['qualification'])
        if not professional:
            notes.append('No source-supported named professional email')
        if portfolio == 'Unknown':
            notes.append('Portfolio size unknown')

        row = [
            None, c['company_id'] or '', name, website,
            fval('berlin_presence'), fval('address'), fval('city'),
            fval('residential_management'), fval('weg_management'),
            fval('commercial_management'), portfolio,
            fval('heating_billing_relevance'), fval('portfolio_complexity'),
            fval('digital_operations_fit'),
            scoring['score'] if scoring['score'] is not None else '',
            scoring['priority'], scoring['qualification'], scoring['completeness'],
            top['name'] if top and top['name'] else 'Unknown',
            top['role'] if top and top['role'] else 'Unknown',
            general or 'Unknown', professional or 'Unknown',
            (top['phone'] if top and top['phone'] else
             next((p['phone'] for p in people if p['phone']), 'Unknown')),
            top['linkedin_url'] if top and top['linkedin_url'] else 'Unknown',
            c['status'], c['source_url'], c['last_researched'] or '',
            '; '.join(notes),
        ]
        all_items.append((c, f, scoring, people, row))

    def sort_key(item):
        c, f, score, people, master_row = item
        status_order = 0 if score['score'] is not None else (1 if c['status'] == 'researched' else 2)
        number = score['score'] if score['score'] is not None else -1
        return status_order, -number, -(score['completeness'] or 0), str(master_row[2]).lower()

    all_items.sort(key=sort_key)
    for idx, item in enumerate(all_items, 1):
        item[4][0] = idx
    return all_items, facts


def add_dashboard(wb, records, issue_count, evidence_count):
    """A concise business-facing dashboard; statistics come from Python records."""
    dash = wb['Dashboard']
    dash.sheet_view.showGridLines = False
    dash.sheet_view.zoomScale = 85
    for col in range(1, 13):
        dash.column_dimensions[get_column_letter(col)].width = 15

    nonduplicate = [r for r in records if r[0]['status'] != 'duplicate']
    qualified = [
        r for r in nonduplicate
        if r[0]['status'] == 'researched' and r[2]['score'] is not None
    ]
    high_priority = sum(r[2]['priority'] == 'High' for r in qualified)
    researched = sum(r[0]['status'] == 'researched' for r in nonduplicate)
    duplicates = len(records) - len(nonduplicate)
    pending = sum(r[0]['status'] in ('new', 'retry') for r in nonduplicate)
    professional_count = 0
    general_count = 0
    for c, facts, score, people, master_row in qualified:
        professional, general, _ = find_company_emails(people, facts)
        professional_count += bool(professional)
        general_count += bool(general)
    no_professional = len(qualified) - professional_count

    dash.merge_cells('A1:L2')
    dash['A1'] = 'HEIDI  /  BERLIN PROPERTY MANAGEMENT LEADS'
    dash['A1'].fill = PatternFill('solid', fgColor=NAVY)
    dash['A1'].font = Font(name='Aptos Display', size=20, bold=True, color=WHITE)
    dash['A1'].alignment = Alignment(vertical='center', indent=1)
    dash.row_dimensions[1].height = 28
    dash.row_dimensions[2].height = 28
    

    def section(row, title):
        dash.merge_cells(start_row=row, start_column=1, end_row=row, end_column=12)
        for col in range(1, 13):
            dash.cell(row, col).fill = PatternFill('solid', fgColor=BLUE)
        cell = dash.cell(row, 1)
        cell.value = title
        cell.font = Font(name='Aptos', size=11, bold=True, color=WHITE)
        cell.alignment = Alignment(vertical='center', indent=1)
        dash.row_dimensions[row].height = 27

    def card(first_col, last_col, top_row, label, value, background='EDF3F7'):
        # Rectangular KPI card without charts, percentage labels or progress bars.
        for row in range(top_row, top_row + 4):
            for col in range(first_col, last_col + 1):
                dash.cell(row, col).fill = PatternFill('solid', fgColor=background)
        dash.merge_cells(start_row=top_row, start_column=first_col,
                         end_row=top_row, end_column=last_col)
        dash.merge_cells(start_row=top_row + 1, start_column=first_col,
                         end_row=top_row + 3, end_column=last_col)
        label_cell = dash.cell(top_row, first_col)
        label_cell.value = label
        label_cell.font = Font(name='Aptos', size=10, bold=True, color=TEXT)
        label_cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        number_cell = dash.cell(top_row + 1, first_col)
        number_cell.value = value
        number_cell.font = Font(name='Aptos Display', size=23, bold=True, color=TEAL)
        number_cell.alignment = Alignment(horizontal='center', vertical='center')
        dash.row_dimensions[top_row].height = 34
        for row in range(top_row + 1, top_row + 4):
            dash.row_dimensions[row].height = 19

    section(5, '01   LEAD PIPELINE')
    card(1, 3, 6, 'Discovered candidates', len(records))
    card(4, 6, 6, 'Researched', researched)
    card(7, 9, 6, 'Qualified leads', len(qualified), GREEN)
    card(10, 12, 6, 'High-priority leads', high_priority, GREEN)

    section(12, '02   CONTACT READINESS  /  QUALIFIED LEADS')
    card(1, 4, 13, 'With professional email', professional_count, GREEN)
    card(5, 8, 13, 'With general email', general_count)
    card(9, 12, 13, 'Without professional email', no_professional, AMBER)


  
    dash.freeze_panes = 'A5'


def export_excel(db, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records, raw_facts = load_records(db)
    wb = Workbook()
    dash = wb.active
    dash.title = 'Dashboard'

    master = prepare_sheet(wb, 'Master Companies', M_HEADERS, {
        'Rank': 9, 'Company ID': 12, 'Company Name': 39, 'Website': 43,
        'Address': 33, 'Managed Apartments / Units': 24, 'Lead Score / 100': 18,
        'Data Completeness %': 20, 'Best Contact Name': 29,
        'General Email': 36, 'Professional Email': 38,
        'Original Source': 40, 'Review Notes': 58,
        'Qualification': 31, 'Research Status': 19, 'LinkedIn': 39,
    })
    write_rows(
        master,
        [r[4] for r in records if r[0]['status'] != 'duplicate'],
        url_columns=(4, 24, 26),
        score_column=15,
    )

    cont = prepare_sheet(wb, 'Contacts', CONTACT_HEADERS, {
        'Company Name': 40, 'Contact Name': 32,
        'General Email': 36, 'Professional Email': 39,
        'Source URL': 50, 'Evidence Quote': 65, 'LinkedIn': 46,
    })
    contact_rows = []
    for c, facts, score, people, master_row in records:
        for person in people:
            professional, general = classify_contact_email(person)
            contact_rows.append([
                master_row[2], c['company_id'],
                score['score'] if score['score'] is not None else '',
                score['priority'], person['name'], person['role'],
                general or 'Unknown', professional or 'Unknown',
                person['phone'], person['linkedin_url'],
                person['source_url'], person['quote'],
            ])
    write_rows(cont, contact_rows, url_columns=(10, 11), score_column=3)

    evid = prepare_sheet(wb, 'Evidence', EVIDENCE_HEADERS, {
        'Company Name': 40, 'Field': 31, 'Verified Value': 39,
        'Source URL': 53, 'Exact Supporting Quote': 83, 'Verified UTC': 27,
    })
    evidence_rows = []
    for c, facts, score, people, master_row in records:
        for fact in raw_facts.get(c['company_id'], []):
            evidence_rows.append([
                master_row[2], c['company_id'], fact['field'], fact['value'],
                fact['source_url'], fact['quote'], fact['verified_at'],
            ])
    write_rows(evid, evidence_rows, url_columns=(5,))

    score_sheet = prepare_sheet(wb, 'Score Breakdown', SCORE_HEADERS, {
        'Company Name': 40, 'Qualification': 33, 'KPI': 38,
        'Reason': 58, 'Evidence URL': 48,
    })
    score_rows = []
    for c, facts, score, people, master_row in records:
        if not c['company_id']:
            continue
        for kpi, points, maximum, reason, source in score['breakdown']:
            score_rows.append([
                master_row[2], c['company_id'], score['qualification'],
                score['score'] if score['score'] is not None else '',
                kpi, points, maximum, reason, source,
            ])
    write_rows(score_sheet, score_rows, url_columns=(9,), score_column=4)

    issues = prepare_sheet(wb, 'Quality Review', ISSUES_HEADERS, {
        'Company Name': 42, 'Issue Code': 29,
        'Detail': 85, 'Logged UTC': 30,
    })
    issue_rows = []
    name_by_candidate = {r[0]['id']: r[4][2] for r in records}
    status_by_candidate = {r[0]['id']: r[0]['status'] for r in records}
    for problem in db.execute('SELECT * FROM issues ORDER BY id').fetchall():
        issue_rows.append([
            name_by_candidate.get(problem['candidate_id'], 'Unknown'),
            problem['candidate_id'],
            status_by_candidate.get(problem['candidate_id'], ''),
            problem['issue_code'], problem['detail'], problem['created_at'],
        ])
    for c, facts, score, people, master_row in records:
        if c['status'] == 'researched' and (score['score'] is None or not people):
            issue_rows.append([
                master_row[2], c['id'], c['status'], 'MISSING_VERIFIED_FIELDS',
                master_row[-1], str(c['last_researched'] or ''),
            ])
    write_rows(issues, issue_rows)

    candidates = prepare_sheet(wb, 'All Candidates', CANDIDATE_HEADERS, {
        'Name Hint': 40, 'Candidate URL': 53,
        'Source URL': 53, 'Last Error': 65,
    })
    write_rows(candidates, [
        [c['id'], c['name_hint'], c['url'], c['source_url'], c['kind'],
         c['status'], c['attempts'], c['last_error']]
        for c, facts, score, people, master_row in records
    ], url_columns=(3, 4))

    rules = prepare_sheet(
        wb, 'Scoring Rules', ['Criterion', 'Maximum Points', 'Scoring Principle'],
        {'Criterion': 42, 'Maximum Points': 21, 'Scoring Principle': 94},
    )
    write_rows(rules, [
        ['Berlin presence', 'Mandatory', 'Verified operating presence / address in Berlin; without it, no score'],
        ['Residential or WEG management', 30, 'Verified residential or WEG management earns 30 points; otherwise no score'],
        ['Managed portfolio size', 25, '>=1000:25, >=300:18, >=100:12, 1-99:5; unknown:0'],
        ['Heating / billing relevance', 20, 'Specific evidence of heating, consumption or related billing earns 20'],
        ['Portfolio complexity', 15, 'Evidence of multiple buildings or a diverse portfolio earns 15'],
        ['Digital / operational fit', 10, 'Published digital portal or operations services earns 10'],
        ['Completeness', 'Separate metric', 'Evidence coverage; missing facts do not imply absence'],
        ['Provisional score', '0-100', 'Score only if Berlin AND residential/WEG management evidence is available'],
    ])

    guide = prepare_sheet(wb, 'Read Me', ['Topic', 'Explanation'], {
        'Topic': 35, 'Explanation': 102,
    })
    write_rows(guide, [
        ['Master Companies', 'One row per nonduplicate discovered candidate, ranked by provisional lead score.'],
        ['Contacts', 'General Email is a shared inbox. Professional Email requires a named person and supporting source quote.'],
        ['Email classification', 'Addresses without adequate evidence remain in the local database, not presented as verified direct emails.'],
        ['Dashboard', 'All counts are calculated in Python from SQLite research records, not by reading Excel cells.'],
        ['Evidence', 'Stored excerpts and URLs help audit each extracted fact; an excerpt alone does not prove correct interpretation.'],
        ['Lead Score', 'Provisional weighted fit based only on available fields; see Score Breakdown for details.'],
        ['Quality Review', 'Review flags are issues to inspect, not a count of incorrect companies.'],
        ['When to submit', 'Manually check selected priority leads and contact details against their original sources.'],
        ['Search limits', 'Discovery and Gemini research are separate from this offline export; this script does not make API calls.'],
    ])

    add_dashboard(wb, records, len(issue_rows), len(evidence_rows))
    wb.active = 0
    wb.save(path)
    return path
