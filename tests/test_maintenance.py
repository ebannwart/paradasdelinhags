import unittest
import test_app as fixtures
from importer import import_file
from modalities import modality

row,workbook=fixtures.row,fixtures.workbook


class MaintenanceTests(unittest.TestCase):
    setUp=fixtures.ApplicationTests.setUp
    tearDown=fixtures.ApplicationTests.tearDown
    post=fixtures.ApplicationTests.post
    load=fixtures.ApplicationTests.load

    def report(self,equipment='L1',files=None):
        response=self.post('/api/maintenance',{'equipment':equipment,'files':files or []})
        self.assertEqual(response.status_code,200,response.json)
        return response.json

    def test_calendar_formulas_and_event_count(self):
        self.load([
            row(start='2026-01-01 00:00',end='2026-01-01 00:00',minutes=0,responsible='OP-OPERAÇÃO'),
            row(start='2026-01-02 10:00',end='2026-01-02 11:00',minutes=60,responsible='ME-MANUTENÇÃO ELÉTRICA'),
            row(start='2026-01-02 11:01',end='2026-01-02 11:31',minutes=30,responsible='MM-MANUTENÇÃO MECÂNICA'),
            row(start='2026-01-03 10:00',end='2026-01-03 12:00',minutes=120,responsible='PP-PROGRAMAÇÃO',reason='MP'),
            row(start='2026-01-31 23:59',end='2026-01-31 23:59',minutes=0,responsible='OP-OPERAÇÃO')])
        data=self.report();month=data['monthly'][0]
        self.assertEqual(month['calendar_minutes'],31*24*60)
        self.assertEqual((month['corrective_minutes'],month['preventive_minutes'],month['failures']),(90,120,1))
        self.assertAlmostEqual(month['imc'],90/44640*100)
        self.assertAlmostEqual(month['dgfm'],(1-210/44640)*100)
        self.assertAlmostEqual(month['mtbf'],(44640-90)/60)
        self.assertEqual(month['mttr'],90)
        self.assertTrue(data['annual'][0]['partial'])
        self.assertIsNone(data['monthly'][1]['imc'])

    def test_leap_year_and_partial_source_month(self):
        self.load([row(start='2024-02-01 10:00',end='2024-02-01 11:00',minutes=60),
                   row(start='2024-02-29 10:00',end='2024-02-29 11:00',minutes=60)])
        data=self.report()
        self.assertEqual(data['latest_year'],2024)
        self.assertEqual(data['monthly'][1]['calendar_hours'],29*24)
        self.assertFalse(data['monthly'][1]['partial'])
        self.load([row(start='2026-09-01 10:00',end='2026-09-01 11:00'),
                   row(start='2026-09-15 10:00',end='2026-09-15 11:00')])
        data=self.report()
        self.assertEqual(data['monthly'][8]['calendar_hours'],15*24)
        self.assertTrue(data['monthly'][8]['partial'])
        self.assertIsNone(data['monthly'][9]['dgfm'])

    def test_no_corrective_failures_and_preventive_responsible(self):
        self.load([row(responsible='ZHST MANUTENÇÃO PREVENTIVA',minutes=60),
                   row(start='2026-01-01 15:00',end='2026-01-01 16:00',minutes=60,responsible='PP-PROGRAMAÇÃO',reason='Reparo Geral')])
        month=self.report()['monthly'][0]
        self.assertEqual(month['modalities']['Preventiva'],120)
        self.assertEqual(month['modalities']['PP'],0)
        self.assertEqual(month['imc'],0)
        self.assertAlmostEqual(month['dgfm'],(1-120/1440)*100)
        self.assertIsNone(month['mtbf']);self.assertIsNone(month['mttr'])
        self.assertEqual(month['failure_events'],0)

    def test_month_boundary_split_and_annual_distinct_failures(self):
        self.load([row(start='2026-01-01 00:00',end='2026-01-01 00:00',minutes=0,responsible='OP'),
                   row(start='2026-01-31 23:30',end='2026-02-01 00:30',minutes=60),
                   row(start='2026-02-28 10:00',end='2026-02-28 11:00',minutes=60,responsible='OP')])
        data=self.report();jan,feb=data['monthly'][:2];year=data['annual'][0]
        self.assertEqual((jan['corrective_minutes'],feb['corrective_minutes']),(30,30))
        self.assertEqual((jan['failures'],feb['failures'],year['failures']),(1,1,1))
        self.assertEqual(year['corrective_minutes'],60)
        self.assertAlmostEqual(year['imc'],60/((31+28)*1440)*100)
        self.assertEqual(year['mttr'],60)
        self.assertEqual(year['failure_events'],0.5)
        self.assertEqual((jan['failure_events'],feb['failure_events']),(1,1))

    def test_targets_are_per_line_persistent_and_validated(self):
        self.load([row(),row(equipment='L2')])
        targets={'imc':1.5,'dgfm':95,'mtbf':0,'mttr':120,'failure_events':12.5}
        self.assertEqual(self.post('/api/maintenance/targets',{'equipment':'L1','targets':targets}).status_code,200)
        self.assertEqual(self.report()['targets'],targets)
        self.assertTrue(all(value is None for value in self.report('L2')['targets'].values()))
        invalid=targets|{'imc':101}
        self.assertEqual(self.post('/api/maintenance/targets',{'equipment':'L1','targets':invalid}).status_code,400)
        self.assertEqual(self.report()['targets'],targets)
        self.assertEqual(self.post('/api/maintenance/targets',{'equipment':'L1','targets':targets|{'mttr':float('nan')}}).status_code,400)
        self.post('/api/maintenance/targets',{'equipment':'L1','targets':{key:None for key in targets}})
        self.assertTrue(all(value is None for value in self.report()['targets'].values()))

    def test_minutes_outside_latest_source_coverage_are_disclosed(self):
        self.load([row(start='2026-09-01 00:00',end='2026-09-01 00:00',minutes=0,responsible='OP'),
                   row(start='2026-09-30 23:00',end='2026-10-01 01:00',minutes=120)])
        data=self.report()
        self.assertEqual(data['monthly'][8]['corrective_minutes'],60)
        self.assertEqual(data['outside_minutes'],60)
        self.assertIsNone(data['monthly'][9]['imc'])

    def test_modalities_are_exclusive_and_manual_override_updates_reports(self):
        cases=[('ME-Manutenção Elétrica','ME'),('MM-Manutenção Mecânica','MM'),('OP-Operação','OP'),
               ('ST-Setup','ST'),('PP-Programação','PP'),('UT-Utilidades','EX'),('ZHST OUTROS','EX')]
        for source,expected in cases:
            self.assertEqual(modality(source,'','Demais paradas',None),expected)
            self.assertEqual(modality(source,'','Manutenção Preventiva',None),'Preventiva')
        self.load([row(responsible='PP-PROGRAMAÇÃO',reason='MP',minutes=10)])
        records=self.post('/api/records',{}).json['rows']
        self.assertEqual(records[0]['modality'],'Preventiva')
        self.assertEqual(self.post('/api/summary',{'modality':['PP']}).json['totals']['records'],0)
        self.post('/api/classify',{'ids':[records[0]['id']],'field':'type_override','value':'Demais paradas'})
        self.assertEqual(self.post('/api/summary',{'modality':['PP']}).json['totals']['records'],1)
        self.assertEqual(self.report()['monthly'][0]['modalities']['PP'],10)
        self.assertEqual(self.report()['monthly'][0]['preventive_minutes'],0)

    def test_file_selection_and_overlapping_source_coverage(self):
        self.load([row()]);other=self.root/'copy.xlsx';workbook(other,[row()]);import_file(self.path,other)
        data=self.report();self.assertEqual(data['monthly'][0]['calendar_minutes'],1440)
        self.assertEqual(data['monthly'][0]['corrective_minutes'],10)
        newer=self.root/'2027.xlsx';workbook(newer,[row(start='2027-01-01 10:00',end='2027-01-01 10:20')]);import_file(self.path,newer)
        self.assertEqual(self.report()['latest_year'],2027)
        first=self.client.get('/api/meta').json['files'][0]['id']
        self.assertEqual(self.report(files=[first])['latest_year'],2026)

    def test_missing_line_month_does_not_assume_availability(self):
        self.load([row(),row(equipment='L2',start='2026-02-01 10:00',end='2026-02-01 11:00')])
        data=self.report()
        self.assertIsNone(data['monthly'][1]['imc'])
        self.assertEqual(data['annual'][0]['months_with_data'],1)
        self.assertEqual(data['annual'][0]['failure_events'],1)
        self.assertIsNone(data['monthly'][1]['failure_events'])
        self.assertEqual(data['annual'][0]['calendar_minutes'],31*1440)

    def test_invalid_percentage_is_unavailable_and_zero_duration_flagged(self):
        self.load([row(minutes=2000,start='2026-01-01 10:00',end='2026-01-01 10:00')])
        month=self.report()['monthly'][0]
        self.assertIsNone(month['imc']);self.assertIsNone(month['dgfm']);self.assertIsNone(month['mtbf'])
        self.assertEqual(month['zero_duration'],1)
        self.assertTrue(month['errors'])

    def test_route_and_line_validation(self):
        self.assertEqual(self.client.get('/kpi-manutencao').status_code,200)
        self.assertEqual(self.post('/api/maintenance',{'equipment':'unknown'}).status_code,400)

    def test_existing_mttr_targets_are_converted_to_minutes_once(self):
        from database import connect, initialize
        with connect(self.path) as db:
            db.execute("DELETE FROM settings WHERE key='mttr_unit'")
            db.execute("INSERT INTO maintenance_targets VALUES ('L1','mttr',2)")
            db.execute("INSERT INTO maintenance_targets VALUES ('L1','mtbf',40)")
        initialize(self.path)
        initialize(self.path)
        with connect(self.path) as db:
            targets={r['indicator']:r['value'] for r in db.execute('SELECT * FROM maintenance_targets')}
        self.assertEqual(targets,{'mttr':120,'mtbf':40})

    def test_event_average_includes_observed_month_without_failures(self):
        self.load([row(),row(start='2026-02-10 10:00',end='2026-02-10 11:00',responsible='OP')])
        data=self.report()
        self.assertEqual(data['annual'][0]['failure_events'],0.5)
        self.assertEqual(data['monthly'][1]['failure_events'],0)
        self.assertIsNone(data['monthly'][2]['failure_events'])

    def test_old_target_schema_migrates_without_losing_targets(self):
        from database import connect, initialize
        with connect(self.path) as db:
            db.execute('DROP TABLE maintenance_targets')
            db.execute("""CREATE TABLE maintenance_targets (
                equipment TEXT NOT NULL, indicator TEXT NOT NULL CHECK(indicator IN ('imc','dgfm','mtbf','mttr')),
                value REAL NOT NULL CHECK(value >= 0), PRIMARY KEY(equipment,indicator))""")
            db.execute("INSERT INTO maintenance_targets VALUES ('L1','mttr',120)")
        initialize(self.path)
        initialize(self.path)
        with connect(self.path) as db:
            db.execute("INSERT INTO maintenance_targets VALUES ('L1','failure_events',12.5)")
            values={r['indicator']:r['value'] for r in db.execute('SELECT * FROM maintenance_targets')}
        self.assertEqual(values,{'mttr':120,'failure_events':12.5})


if __name__=='__main__':unittest.main()
