import json
import tempfile
import unittest
from pathlib import Path
from app import create_app
from database import connect


class LocalSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.path=self.root/'shared.sqlite3'
        self.profile=self.root/'user1'
        self.app=create_app(self.path,self.root,local_dir=self.profile)
        self.client=self.app.test_client()
        self.client.get('/configuracoes')
        with self.client.session_transaction() as session:
            self.headers={'X-CSRF-Token':session['csrf']}

    def tearDown(self):
        self.temp.cleanup()

    def post(self,url,body):
        return self.client.post(url,json=body,headers=self.headers)

    def test_profiles_isolate_paths_and_share_offenders(self):
        with connect(self.path) as db:
            db.execute("INSERT INTO offenders(name,name_key) VALUES('Motor','motor')")
        url='/api/configuration/sources'
        self.assertEqual(self.post(url,dict(section='failure',path=str(self.root/'one.xls'),page_size=50)).status_code,200)
        other=create_app(self.path,self.root,local_dir=self.root/'user2').test_client()
        self.assertEqual(self.client.get('/api/configuration').json['sources']['failure_page_size'],50)
        self.assertEqual(other.get('/api/configuration').json['sources']['failure_page_size'],15)
        self.assertNotEqual(self.client.get('/api/configuration').json['sources']['failure'],other.get('/api/configuration').json['sources']['failure'])
        self.assertEqual(other.get('/api/offender-actions').json['offenders'][0]['name'],'Motor')
        with connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='application_sources'").fetchone())
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'delete')

    def test_copy_no_overwrite_and_restart_only(self):
        with connect(self.path) as db:
            db.execute("INSERT INTO offenders(name,name_key) VALUES('Motor','motor')")
        target=self.root/'copy.sqlite3'
        url='/api/configuration/database'
        self.assertEqual(self.post(url,dict(path=str(target),mode='copy')).status_code,200)
        self.assertEqual(self.app.config['DB_PATH'],str(self.path))
        state=self.client.get(url).json
        self.assertTrue(state['pending']);self.assertEqual(state['selected'],str(target))
        with connect(target) as db:
            self.assertEqual(db.execute('SELECT name FROM offenders').fetchone()[0],'Motor')
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'delete')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sap_source_choices').fetchone()[0],0)
        self.assertEqual(self.post(url,dict(path=str(target),mode='copy')).status_code,400)
        restarted=create_app(source_dir=self.root,local_dir=self.profile)
        self.assertEqual(restarted.config['DB_PATH'],str(target))
        self.assertFalse(restarted.test_client().get(url).json['pending'])
        self.assertEqual(self.post(url,dict(path=str(self.path),mode='existing')).status_code,200)
        self.assertFalse(self.client.get(url).json['pending'])

    def test_invalid_paths_and_missing_selected_database(self):
        url='/api/configuration/database'
        self.assertEqual(self.client.post(url,json={}).status_code,403)
        for path in ['relative.sqlite3',str(self.root/'missing.sqlite3')]:
            self.assertEqual(self.post(url,dict(path=path)).status_code,400)
        bad=self.root/'wrong.sqlite3';bad.write_text('not a database')
        self.assertNotEqual(self.post(url,dict(path=str(bad))).status_code,200)
        self.assertFalse((self.profile/'database.json').exists())
        (self.profile/'database.json').write_text(json.dumps({'path':str(self.root/'offline.sqlite3')}))
        with self.assertRaises(ValueError):
            create_app(source_dir=self.root,local_dir=self.profile)
        self.assertFalse((self.root/'offline.sqlite3').exists())
