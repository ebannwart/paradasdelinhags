import unittest
import test_app as fixtures
from database import connect
from failure_analysis import import_snapshot
from test_failure_analysis import export


class OffenderActionsTests(unittest.TestCase):
    setUp=fixtures.ApplicationTests.setUp
    tearDown=fixtures.ApplicationTests.tearDown
    post=fixtures.ApplicationTests.post
    load=fixtures.ApplicationTests.load

    def prepare(self):
        self.load([fixtures.row(equipment='LSL1',start='2026-09-30 10:00',end='2026-09-30 11:00')])
        with connect(self.path) as db:
            self.offender=db.execute("INSERT INTO offenders(name,name_key) VALUES('Sensor','sensor')").lastrowid
            db.execute('UPDATE records SET offender_id=?',(self.offender,))
        self.snapshot('Aberta')

    def snapshot(self,status,note='100'):
        return import_snapshot(self.path,export([{'Nota':note,'Hora parada processo':'10:00:00','Texto das Medidas':'Trocar sensor','Item Medida':'0010','Status Medida':status,'Data planejada medida(fim)':'01.01.2020'}]),'ZPMX.xls')

    def data(self):
        r=self.client.get('/api/offender-actions',query_string={'offender':self.offender})
        self.assertEqual(r.status_code,200)
        return r.json

    def link(self,linked=True,note='100'):
        return self.post('/api/offender-actions/link',{'offender':self.offender,'note':note,'linked':linked})

    def test_suggestion_requires_confirmation_and_status_updates(self):
        self.prepare()
        note=self.data()['notes'][0]
        self.assertTrue(note['automatic']);self.assertTrue(note['linked'])
        self.assertEqual(len(note['evidence']),1)
        self.assertEqual(self.link().status_code,200)
        self.link()  # Idempotent: actions and links must not be duplicated.
        self.snapshot('Concluída')
        note=self.data()['notes'][0]
        self.assertTrue(note['linked']);self.assertFalse(note['suggested'])
        self.assertEqual(note['actions'][0]['state'],'Concluída')
        self.assertEqual(len(note['actions']),1)
        self.assertEqual(self.link(False).status_code,200)
        self.assertTrue(self.data()['notes'][0]['automatic'])

    def test_absent_note_is_historical_and_recovers_on_return(self):
        self.prepare();self.link();self.snapshot('Aberta',note='200')
        old=next(n for n in self.data()['notes'] if n['id']=='100')
        self.assertTrue(old['linked']);self.assertTrue(old['stale'])
        self.snapshot('Concluída')
        note=self.data()['notes'][0]
        self.assertTrue(note['linked']);self.assertFalse(note['stale'])

    def test_validation_csrf_and_no_automatic_link(self):
        self.prepare()
        self.assertEqual(self.link(note='missing').status_code,400)
        self.assertEqual(self.client.post('/api/offender-actions/link',json={'linked':True}).status_code,403)
        with connect(self.path) as db:
            db.execute("UPDATE records SET equipment='LZG1'")
        note=self.data()['notes'][0]
        self.assertFalse(note['suggested']);self.assertFalse(note['linked'])
        self.assertEqual(self.link().status_code,200)  # Manual cross-source confirmation remains possible.

    def test_empty_import(self):
        with connect(self.path) as db:
            self.offender=db.execute("INSERT INTO offenders(name,name_key) VALUES('Sensor','sensor')").lastrowid
        self.assertEqual(self.data()['notes'],[])
        self.assertIsNone(self.data()['snapshot'])

    def test_edit_location_mapping_and_preserve_confirmed_links(self):
        self.prepare()
        self.link()
        url='/api/offender-actions/mappings'
        initial=self.client.get(url).json['mappings']
        self.assertEqual(initial[0]['equipment'],'LSL1')
        rows=[{'local':'g-csn-79-002','equipment':'LSL1'}]
        self.assertEqual(self.post(url,{'mappings':rows}).status_code,200)
        self.assertEqual(self.client.get(url).json['mappings'][0]['local'],'G-CSN-79-002')
        self.snapshot('Concluída')
        self.assertEqual(self.client.get(url).json['mappings'][0]['local'],'G-CSN-79-002')
        self.assertEqual(self.post(url,{'mappings':[]}).status_code,200)
        self.assertEqual(self.client.get(url).json['mappings'],[])
        n=self.data()['notes'][0]
        self.assertTrue(n['linked']);self.assertEqual(n['equipment'],'')
        self.assertFalse(n['suggested'])

    def test_invalid_mapping_does_not_overwrite(self):
        self.prepare();url='/api/offender-actions/mappings'
        original=self.client.get(url).json['mappings']
        for rows in [[{'local':'A','equipment':'missing'}],
                     [{'local':'','equipment':'LSL1'}],original+original]:
            self.assertEqual(self.post(url,{'mappings':rows}).status_code,400)
            self.assertEqual(self.client.get(url).json['mappings'],original)
        self.assertEqual(self.client.post(url,json={'mappings':[]}).status_code,403)

    def test_mapping_specificity_and_segment_boundary(self):
        from offender_actions import mapped_equipment
        rows=[{'local':'G-CSN-79','equipment':'LSL1'},
              {'local':'G-CSN-79-002','equipment':'LZG1'}]
        self.assertEqual(mapped_equipment('G-CSN-79-002-023',rows),'LZG1')
        self.assertEqual(mapped_equipment('G-CSN-79-002',rows),'LZG1')
        self.assertEqual(mapped_equipment('G-CSN-79-003',rows),'LSL1')
        self.assertEqual(mapped_equipment('G-CSN-790-002',rows),'')

    def test_automatic_match_uses_time_line_and_midnight(self):
        from offender_actions import matching_launches
        n={'equipment':'LSL1','date':'2026-09-30','time':'00:10:00'}
        r={'equipment':'LSL1','start':'2026-09-29T23:50:00','end':'2026-09-30T00:20:00'}
        self.assertEqual(matching_launches(n,[r]),[r])
        self.assertEqual(matching_launches(n|{'time':'00:20:00'},[r]),[r])
        self.assertEqual(matching_launches(n|{'time':''},[r]),[])
        self.assertEqual(matching_launches(n|{'equipment':'LZG1'},[r]),[])
        self.assertEqual(matching_launches(n|{'time':'13:00:00'},[r]),[])

    def test_automatic_actions_need_no_confirmation(self):
        self.prepare()
        n=self.data()['notes'][0]
        self.assertTrue(n['automatic']);self.assertTrue(n['linked'])
        self.assertFalse(n['manual_linked']);self.assertEqual(len(n['actions']),1)
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM offender_failure_links').fetchone()[0],0)
            db.execute("UPDATE records SET start='2026-09-30T14:00:00',end='2026-09-30T15:00:00'")
        self.assertFalse(self.data()['notes'][0]['linked'])

    def test_full_intervals_overlap_and_touching_endpoints(self):
        from offender_actions import matching_launches
        r={'equipment':'LSL1','start':'2026-09-30T12:59:00','end':'2026-09-30T13:14:00'}
        n={'equipment':'LSL1','date':'2026-09-30','time':'12:58:00','process_duration':2/60}
        self.assertEqual(matching_launches(n,[r]),[r])  # One minute of overlap.
        self.assertEqual(matching_launches(n|{'process_duration':1/60},[r]),[r])
        self.assertEqual(matching_launches(n|{'time':'13:14:00'},[r]),[r])
        self.assertEqual(matching_launches(n|{'time':'12:00:00','process_duration':2},[r]),[r])
        self.assertEqual(matching_launches(n|{'process_duration':0},[r]),[])
        self.assertEqual(matching_launches(n|{'process_duration':None},[r]),[])
        self.assertEqual(matching_launches(n|{'time':'13:14:01'},[r]),[])
        self.assertEqual(matching_launches(n|{'equipment':'LZG1'},[r]),[])
        overnight={'equipment':'LSL1','start':'2026-10-01T00:00:00','end':'2026-10-01T00:10:00'}
        self.assertEqual(matching_launches(n|{'time':'23:59:00'},[overnight]),[overnight])
