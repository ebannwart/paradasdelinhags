import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_sap_plan as fixtures
from database import connect
from sap_plan import import_exports


class SAPProfilesTests(unittest.TestCase):
    setUp=fixtures.SAPPlanTests.setUp
    tearDown=fixtures.SAPPlanTests.tearDown
    post=fixtures.SAPPlanTests.post

    def create(self,name='Centro de Serviços'):
        r=self.post('profiles',{'name':name})
        self.assertEqual(r.status_code,200,r.json)
        return r.json['id']

    def test_profiles_isolate_imports_rules_and_details(self):
        ident=self.create()
        original=self.client.get('/api/sap/meta').json
        self.assertTrue(original['assets'])
        self.assertEqual(self.client.get(f'/api/sap/meta?profile={ident}').json['assets'],[])
        # Same item/plan identifiers across origins must coexist.
        rows={'IP18':[{'plan':'P','item':'I','asset':'OTHER-001','item_text':'Outro plano'}],
              'IW39':[{'plan':'P','item':'I','order':'X','asset':'OTHER-001','basic_start':'2026-09-01','system_status':'CONF'}]}
        with patch('sap_plan.read_export',side_effect=lambda path,kind:iter(rows[kind])):
            import_exports(self.path,self.root,[(self.root/'IP18.xlsx','IP18'),(self.root/'IW39.xlsx','IW39')],profile_id=ident)
        second=self.client.get(f'/api/sap/meta?profile={ident}').json
        self.assertEqual(second['assets'][0]['asset'],'OTHER-001')
        self.assertEqual(self.client.get('/api/sap/meta').json['assets'],original['assets'])
        self.assertEqual(self.post(f'config?profile={ident}',{'done_user':['TEST']}).status_code,200)
        self.assertEqual(self.client.get('/api/sap/meta').json['config']['done_user'],[])
        self.assertEqual(self.client.get(f'/api/sap/meta?profile={ident}').json['config']['done_user'],['TEST'])
        detail=self.client.get(f'/api/sap/plan-detail?profile={ident}&plan=P').json
        self.assertEqual(len(detail['items']),1)
        self.assertEqual(detail['items'][0]['asset'],'OTHER-001')
        self.assertEqual(len(self.client.get('/api/sap/plan-detail?plan=P').json['items']),4)
        self.assertEqual(self.post(f'export-plans?profile={ident}',{'filters':{}}).status_code,200)
        self.assertEqual(self.post(f'profiles',{'id':ident,'name':'CS'}).status_code,200)

    def test_local_sources_separated_and_unknown_profile_rejected(self):
        ident=self.create()
        choices={k:str(self.root/(k+'.xlsx')) for k in ['IH06','IP18','IP24','IW39','IW49N']}
        r=self.client.post(f'/api/configuration/sources?profile={ident}',json={'section':'plan','choices':choices},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get(f'/api/configuration?profile={ident}').json['sources']['plan'],choices)
        self.assertNotEqual(self.client.get('/api/configuration').json['sources']['plan'],choices)
        self.assertEqual(self.client.get('/api/sap/meta?profile=999').status_code,400)
        self.assertEqual(self.post('report?profile=999',{}).status_code,400)
        self.assertEqual(self.post('profiles',{'name':'Centro de Serviços'}).status_code,400)
        self.assertEqual(self.client.post('/api/sap/profiles',json={'name':'x'}).status_code,403)

    def test_group_changes_cannot_cross_profiles(self):
        ident=self.create()
        self.assertEqual(self.post('groups',{'name':'Grupo','assets':['G-CSN-79-001-010-001']}).status_code,200)
        group=self.client.get('/api/sap/meta').json['groups'][0]['id']
        self.assertEqual(self.post(f'groups/delete?profile={ident}',{'id':group}).status_code,400)
        self.assertEqual(self.post(f'groups/visibility?profile={ident}',{'id':group,'visible':False}).status_code,400)
        self.assertEqual(self.post(f'groups/reorder?profile={ident}',{'ids':[group]}).status_code,400)
        self.assertEqual(len(self.client.get('/api/sap/meta').json['groups']),1)

    def test_legacy_migration_preserves_data_and_is_repeatable(self):
        from sap_plan import initialize
        legacy=self.root/'legacy.sqlite3'
        with connect(legacy) as db:
            db.executescript("""
                CREATE TABLE sap_rows(kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(kind,id));
                CREATE TABLE sap_files(name TEXT PRIMARY KEY,kind TEXT,rows INTEGER,imported_at TEXT);
                CREATE TABLE sap_groups(id INTEGER PRIMARY KEY,name TEXT UNIQUE,assets TEXT);
                CREATE TABLE sap_config(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT);
                INSERT INTO sap_rows VALUES('IP18','I','{}');
                INSERT INTO sap_files VALUES('IP18.xlsx','IP18',1,'2026-01-01');
                INSERT INTO sap_groups VALUES(8,'Grupo legado','[]');
                INSERT INTO sap_config VALUES(1,'{}');
            """)
            initialize(db)
        with connect(legacy) as db:
            initialize(db)
            for table in ['sap_rows','sap_files','sap_groups','sap_config']:
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table} WHERE profile_id=1').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT id FROM sap_groups').fetchone()[0],8)
