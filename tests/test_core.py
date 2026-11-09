"""Synthetic fixtures only. No old companies, real personal data, or network needed."""
import tempfile
from pathlib import Path
import unittest
from pydantic import ValidationError
from openpyxl import load_workbook
from heidi_agent.storage import connect,add_candidate,save_company,add_fact,add_contact,domain_of
from heidi_agent.scoring import best_facts,score_company
from heidi_agent.models import Extraction,ProposedFact,ProposedContact
from heidi_agent.ai_extract import verify_extraction
from heidi_agent.web_research import Page,safe_url
from heidi_agent.export_excel import export_excel
from heidi_agent.method_doc import create_methodology_doc
from heidi_agent.discovery import load_input
from heidi_agent.rules_extract import grounded_rules
from heidi_agent.settings import INPUT

class CleanAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.temp.name)/'brand_new.sqlite3')
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_new_db_empty(self):
        for name in ('candidates','companies','facts','contacts','issues'):
            self.assertEqual(self.db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0],0)

    def test_input_has_only_sources_and_keywords(self):
        sources,keywords=load_input(INPUT)
        self.assertGreaterEqual(len(sources),1)
        self.assertGreaterEqual(len(keywords),1)
        self.assertTrue(all(a in ('directory','company','profile') for a,b in sources))

    def test_dedup(self):
        self.assertTrue(add_candidate(self.db,'https://sample-unique.invalid/'))
        self.assertFalse(add_candidate(self.db,'https://sample-unique.invalid/'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],1)

    def test_grounded_directory_fallback(self):
        p=Page(0,'https://directory.example.net',
            'Muster Wohnen GmbH Jana Beispiel jana.beispiel@sample.org Adresse Allee 1 10117 Berlin')
        facts,contacts=grounded_rules([p])
        self.assertIn('berlin_presence',{x[0] for x in facts})
        self.assertEqual(contacts[0][0],'Jana Beispiel')
        self.assertEqual(contacts[0][2],'jana.beispiel@sample.org')

    def test_public_url_safety(self):
        self.assertFalse(safe_url('http://localhost/admin'))
        self.assertFalse(safe_url('http://127.0.0.1/'))
        self.assertFalse(safe_url('file:///etc/passwd'))
        self.assertTrue(safe_url('https://example.org/unternehmen'))

    def test_grounded_extraction_rejects_made_up_emails(self):
        text='Example Property Verwaltung GmbH provides WEG Verwaltung at Berlin. Contact: Jana Beispiel jana@example.org.'
        page=Page(1,'https://example.org/kontakt',text)
        data=Extraction(facts=[ProposedFact(field='weg_management',value='Yes',page_id=1,quote='WEG Verwaltung'),
                               ProposedFact(field='berlin_presence',value='Yes',page_id=1,quote='Berlin'),
                               ProposedFact(field='portfolio_units',value='800',page_id=1,quote='800 buildings managed')],
                        contacts=[ProposedContact(name='Jana Beispiel',role='',email='invented@example.org',
                                                  page_id=1,quote='Jana Beispiel jana@example.org')])
        facts,contacts,rejected=verify_extraction(data,[page])
        self.assertEqual(len(facts),2)
        self.assertEqual(len(contacts),1)
        self.assertEqual(contacts[0][2],'')
        self.assertTrue(any(c=='contact_email_not_on_page' for c,x in rejected))

    def test_score_missing_berlin_no_score(self):
        s=score_company({'weg_management':{'value':'Yes','source_url':'u'}})
        self.assertIsNone(s['score'])

    def test_scored_ranked_workbook_and_doc(self):
        add_candidate(self.db,'https://b-low.invalid/',name_hint='B Example GmbH')
        add_candidate(self.db,'https://a-high.invalid/',name_hint='A Example GmbH')
        cands=self.db.execute('SELECT * FROM candidates ORDER BY id').fetchall()
        low=save_company(self.db,cands[0]['id'],'B Example GmbH','https://b-low.invalid/')
        high=save_company(self.db,cands[1]['id'],'A Example GmbH','https://a-high.invalid/')
        for ident,name in ((low,'B Example GmbH'),(high,'A Example GmbH')):
            add_fact(self.db,ident,'company_name',name,name,'https://example.org')
            add_fact(self.db,ident,'berlin_presence','Yes','Berlin office','https://example.org')
            add_fact(self.db,ident,'weg_management','Yes','WEG Verwaltung','https://example.org')
        add_fact(self.db,high,'portfolio_units','2500','2500 Wohneinheiten','https://example.org')
        add_fact(self.db,high,'heating_billing_relevance','Yes','Heizkostenabrechnung','https://example.org')
        add_fact(self.db,high,'portfolio_complexity','Yes','Multiple buildings','https://example.org')
        add_fact(self.db,high,'digital_operations_fit','Yes','Digital portal','https://example.org')
        add_contact(self.db,high,'Test Person','Leitung','test@example.org','', '',
                    'Test Person test@example.org','https://example.org/contact')
        self.db.execute("UPDATE candidates SET status='researched'")
        self.db.commit()
        x=Path(self.temp.name)/'result.xlsx'
        d=Path(self.temp.name)/'method.docx'
        export_excel(self.db,x)
        create_methodology_doc(self.db,d)
        self.assertTrue(x.exists())
        self.assertTrue(d.exists())
        wb=load_workbook(x,read_only=True,data_only=True)
        self.assertEqual(len(wb.sheetnames),9)
        sh=wb['Master Companies']
        self.assertEqual(sh['C5'].value,'A Example GmbH')
        self.assertEqual(sh['O5'].value,100)
        self.assertEqual(sh['U5'].value,'test@example.org')
        self.assertEqual(sh['O6'].value,30)
        self.assertEqual(len(list(wb['Contacts'].values)),5)
        self.assertGreaterEqual(len(list(wb['Evidence'].values)),7)
        wb.close()

if __name__=='__main__':
    unittest.main()
