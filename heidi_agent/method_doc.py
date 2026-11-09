"""Generate an honest methodology document with current live run statistics."""
from pathlib import Path
from datetime import date
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from .scoring import WEIGHTS


def create_methodology_doc(db,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    c=db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]
    r=db.execute("SELECT COUNT(*) FROM candidates WHERE status='researched'").fetchone()[0]
    e=db.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    ct=db.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]
    review=db.execute('SELECT COUNT(*) FROM issues').fetchone()[0]
    doc=Document();sec=doc.sections[0]
    sec.top_margin=Inches(.75);sec.bottom_margin=Inches(.7)
    styles=doc.styles
    styles['Normal'].font.name='Aptos';styles['Normal'].font.size=Pt(10)
    styles['Title'].font.name='Aptos Display';styles['Title'].font.size=Pt(21)
    doc.add_heading('Heidi Systems | Berlin Lead Research',0)
    doc.add_paragraph('Approach, automation, quality controls and limitations',style='Subtitle')
    doc.add_paragraph(f'Generated: {date.today().isoformat()}   |   Case study for AI Agent Builder')
    doc.add_heading('1. Goal and business qualification',level=1)
    doc.add_paragraph('Discover property management companies with Berlin operations, verify their published services and portfolio indicators, identify relevant public professional contacts, and create an explainable prioritised lead list for a metering and heating-billing service provider.')
    doc.add_heading('2. Sources and architecture',level=1)
    doc.add_paragraph('Sources are provided in data/input/Heidi_Input.xlsx: company directories, company websites and optional search keywords. The search API (Tavily) is optional; direct directory extraction functions without it. Python, HTTPX, BeautifulSoup, Google Gemini structured extraction, SQLite and OpenPyXL form the pipeline. There is no imported historical database.')
    doc.add_heading('3. Workflow',level=1)
    for x in ['Read URLs and optional keywords from the editable input workbook.',
              'Respect robots.txt, apply request pacing and discover candidate companies.',
              'Visit each public company homepage plus a bounded number of relevant internal pages.',
              'Ask Gemini to return source-tagged structured facts with exact supporting quotes.',
              'Reject extracted claims if the alleged quote is absent from the cited page.',
              'Save verified facts, professional contacts, error flags and progress to SQLite.',
              'Compute explainable qualification scores and export one ranked Excel workbook.']:
        doc.add_paragraph(x,style='List Bullet')
    doc.add_heading('4. Qualification and scoring',level=1)
    doc.add_paragraph('Verified Berlin presence and verified residential or WEG management are mandatory for a provisional score. Missing fields are Unknown rather than false. The weighted score does not replace manual sales judgment.')
    table=doc.add_table(rows=1,cols=2);table.style='Light Shading Accent 1'
    table.rows[0].cells[0].text='Criterion';table.rows[0].cells[1].text='Maximum'
    for k,v in WEIGHTS.items():
        row=table.add_row().cells;row[0].text=k;row[1].text=f'{v} pts'
    doc.add_heading('5. Results from the current local database',level=1)
    doc.add_paragraph(f'Candidates discovered: {c} | Successfully researched: {r} | Verified fact statements: {e} | Named contact records: {ct} | Review flags: {review}.')
    doc.add_paragraph('Counts reflect only actual locally stored records at export time. They are not claims that every candidate is a verified lead.')
    doc.add_heading('6. Validation, ethics and limitations',level=1)
    for x in ['A citation URL and exact quote are retained for every accepted fact.',
              'Hallucinated emails or portfolio numbers are never guessed. Only publicly listed professional contacts are eligible.',
              'Dynamic, blocked or non-HTML websites can fail; such entries require human review.',
              'A quote appearing in a page proves text provenance, not that a company is currently correct; manually audit high-ranked leads.',
              'The free Gemini tier has quotas. The program halts on a quota error and never switches billing tiers.',
              'Potential duplicate entities with different domains and company group structures may require manual merging.',
              'Public email availability does not automatically authorize unsolicited commercial emails under German law.']:
        doc.add_paragraph(x,style='List Bullet')
    doc.add_heading('7. Reproducibility',level=1)
    doc.add_paragraph('Run the batch files in order: SETUP, EDIT_API_KEYS, CHECK_GEMINI and RUN_AGENT. Set max-company and max-page limits in command flags. The SQLite database persists between runs within this project, and Export always regenerates Excel and this methodology document. The distribution itself intentionally contains zero candidate records and no generated outputs.')
    for sec in doc.sections:
        sec.header.paragraphs[0].text='HEIDI SYSTEMS  |  Research workflow'
        sec.footer.paragraphs[0].text='Automated evidence-driven research  •  Manual audit required'
    doc.save(path)
    return path
