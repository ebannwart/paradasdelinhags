import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from configuration import PLAN_KINDS


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbox = self.root / 'Importacao'
        self.inbox.mkdir()
        for name in ['2025.xlsx','2026.xlsx','ZPMX0072.xls', *[k+' planta.xlsx' for k in PLAN_KINDS]]:
            (self.inbox / name).touch()
        self.db = self.root / 'test.sqlite3'
        self.app = create_app(self.db, self.root)
        self.client = self.app.test_client()
        self.client.get('/configuracoes')
        with self.client.session_transaction() as s:
            self.headers = {'X-CSRF-Token':s['csrf']}

    def tearDown(self):
        self.temp.cleanup()

    def save(self, body):
        return self.client.post('/api/configuration/sources', json=body, headers=self.headers)

    def test_discovery_and_persistence_without_silent_reset(self):
        data = self.client.get('/api/configuration').json
        self.assertEqual(len(data['sources']['stops']), 2)
        self.assertEqual(set(data['sources']['plan']), set(PLAN_KINDS))
        self.assertTrue(all(data['existence'].values()))
        custom = str(self.root / 'future' / 'new.xls')
        self.assertEqual(self.save(dict(section='failure', path=custom, page_size=50)).status_code, 200)
        self.assertEqual(self.save(dict(section='stops', paths=[])).status_code, 200)
        client = create_app(self.db, self.root).test_client()
        saved = client.get('/api/configuration').json
        self.assertEqual(saved['sources']['failure'], custom)
        self.assertEqual(saved['sources']['failure_page_size'], 50)
        self.assertEqual(saved['sources']['stops'], [])
        self.assertFalse(saved['existence'][custom])

    def test_validation_and_csrf_do_not_replace_settings(self):
        original = self.client.get('/api/configuration').json['sources']
        self.assertEqual(self.client.post('/api/configuration/sources', json={'section':'stops','paths':[]}).status_code,403)
        self.assertEqual(self.save(dict(section='stops',paths=['a.xlsx','sub/a.xlsx'])).status_code,400)
        self.assertEqual(self.save(dict(section='failure',path='bad.xlsx',page_size=15)).status_code,400)
        self.assertEqual(self.save(dict(section='failure',path='good.xls',page_size=0)).status_code,400)
        self.assertEqual(self.client.get('/api/configuration').json['sources'], original)

    def test_importers_use_saved_addresses(self):
        selected = self.inbox / '2026.xlsx'
        self.save(dict(section='stops', paths=[str(selected)]))
        with patch('app.threading.Thread', side_effect=lambda target,**kwargs:Mock(start=target)), patch('app.import_file', return_value={'status':'unchanged'}) as importer:
            r = self.client.post('/api/import/configured',json={},headers=self.headers)
            self.assertEqual(r.status_code,202)
            self.assertEqual(importer.call_args.args[1],selected)
        with patch('sap_plan.threading.Thread',side_effect=lambda target,**kwargs:Mock(start=target)), patch('sap_plan.import_exports',return_value={'files':5}) as importer:
            r = self.client.post('/api/sap/import',json={},headers=self.headers)
            self.assertEqual(r.status_code,202)
            self.assertEqual({k for _,k in importer.call_args.args[2]},set(PLAN_KINDS))
        with patch('failure_analysis.import_snapshot',return_value={'id':1,'unchanged':True}) as importer:
            r = self.client.post('/api/failures/import',json={},headers=self.headers)
            self.assertEqual(r.status_code,200)
            self.assertEqual(importer.call_args.args[2],'ZPMX0072.xls')

    def test_absent_files_fail_without_falling_back_to_another_source(self):
        self.save(dict(section='failure',path='absent.xls',page_size=25))
        self.assertEqual(self.client.post('/api/failures/import',json={},headers=self.headers).status_code,400)
        self.save(dict(section='stops',paths=['absent.xlsx']))
        self.assertEqual(self.client.post('/api/import/configured',json={},headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/api/failures/data').json['page_size'],25)


if __name__ == '__main__': unittest.main()
