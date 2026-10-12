import io
import tempfile
import unittest
from pathlib import Path

from app import create_app
from failure_analysis import action_state, parse_export


def export(rows, extended=True):
    first = ['', 'Nota', 'Descrição da nota ZC', 'Local de instalação', 'Unidade Operacional',
             'Status da Nota', 'Dta. parada processo', 'Dur. parada Prod.', 'Texto das Medidas',
             'Status Medida', 'Data planejada medida(fim)', 'Data conclusão Medida', 'Item',
             'Dur. parada processo', 'Dta. parada Prod.', 'Cent. Trab. Resp.', 'Perda de Produção']
    second = ['Texto', '', 'Item Medida', 'Porque 1', 'Porque 5']
    lines = ['Descrição Ocorrência e Análise Falha', '', '\t'.join(first)]
    if extended:
        lines.append('\t'.join(second))
    lines.append('')
    for row in rows:
        defaults = {'Nota': '100', 'Descrição da nota ZC': 'Falha',
                    'Local de instalação': 'G-CSN-79-002-023-045-003', 'Unidade Operacional': '023 - LINHA DE SOLDA LASER',
                    'Status da Nota': 'Falha Analisada Medida Cart', 'Dta. parada processo': '30.09.2026',
                    'Dur. parada Prod.': '1,25'} | row
        lines.append('\t'.join(defaults.get(k, '') for k in first))
        if extended:
            lines.append('\t'.join(defaults.get(k, '') for k in second))
    return '\r\n'.join(lines).encode('utf-16')


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root / 'test.sqlite3', self.root)
        self.client = self.app.test_client()
        self.client.get('/analises-de-falha')
        with self.client.session_transaction() as session:
            self.headers = {'X-CSRF-Token': session['csrf']}

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, content):
        return self.client.post('/api/failures/import', data={'file': (io.BytesIO(content), 'ZPMX.xls')}, headers=self.headers)

    def test_parser_preserves_distinct_actions_and_note_duration(self):
        action = {'Item Medida': '1', 'Texto das Medidas': 'Revisar plano', 'Status Medida': 'Aberta',
                  'Porque 1': 'Correia rompeu', 'Porque 5': 'Inspeção ausente'}
        result = parse_export(export([{}, action, action, action | {'Texto das Medidas': 'Incluir ronda'}]))
        self.assertEqual(len(result['notes']), 1)
        self.assertEqual(result['notes'][0]['duration'], 1.25)
        self.assertEqual(len(result['notes'][0]['actions']), 2)
        self.assertEqual(result['notes'][0]['line'], '023')
        self.assertEqual(result['notes'][0]['investigations'][0]['why'][4], 'Inspeção ausente')
        self.assertEqual(len(result['warnings']), 1)

    def test_short_export_and_invalid_continuation(self):
        self.assertEqual(len(parse_export(export([{}], False))['notes']), 1)
        content = export([{}]).decode('utf-16').splitlines()
        with self.assertRaises(ValueError):
            parse_export('\r\n'.join(content[:-1]).encode('utf-16'))
        with self.assertRaises(ValueError):
            parse_export(export([{}, {'Dur. parada Prod.': '2,00'}]))

    def test_line_stop_date_duration_and_sap_filters(self):
        result = parse_export(export([{'Dta. parada processo': '30.09.2026',
                                       'Dta. parada Prod.': '01.10.2026',
                                       'Dur. parada processo': '12,50', 'Dur. parada Prod.': '0,00',
                                       'Cent. Trab. Resp.': 'ME', 'Perda de Produção': 'X'}]))
        note = result['notes'][0]
        self.assertEqual(note['date'], '2026-09-30')
        self.assertEqual(note['production_date'], '2026-10-01')
        self.assertEqual(note['process_duration'], 12.5)
        self.assertEqual(note['duration'], 0)
        self.assertEqual(note['work_center'], 'ME')
        self.assertEqual(note['production_loss'], 'X')
        self.assertEqual(parse_export(export([{}]))['notes'][0]['production_loss'], '')
        with self.assertRaises(ValueError):
            parse_export(export([{'Dur. parada processo': 'NaN'}]))

    def test_legacy_snapshot_is_preserved_on_parser_upgrade(self):
        import hashlib
        import json
        from database import connect
        content = export([{'Cent. Trab. Resp.': 'MM', 'Dur. parada processo': '2,00'}])
        with connect(self.app.config['DB_PATH']) as db:
            db.execute('INSERT INTO failure_snapshots(name,sha,imported_at,payload) VALUES(?,?,?,?)',
                       ('old.xls', hashlib.sha256(content).hexdigest(), '2026-09-30', json.dumps({'notes': [], 'warnings': [], 'rows': 0})))
        new = self.upload(content).json
        data = self.client.get('/api/failures/data').json
        self.assertEqual(len(data['history']), 2)
        self.assertEqual(data['notes'][0]['work_center'], 'MM')
        self.assertEqual(self.upload(content).json['id'], new['id'])
        self.assertEqual(self.client.get('/api/failures/data?snapshot=1').json['notes'], [])

    def test_overdue_and_completed_are_distinct(self):
        action = dict(status='Aberta', due='2026-10-12', completed='')
        self.assertEqual(action_state(action, '2026-10-12'), 'Aberta no prazo')
        self.assertEqual(action_state(action, '2026-10-13'), 'Vencida')
        self.assertEqual(action_state(action | {'status': 'Conc. Após PRAZO'}, '2026-10-13'), 'Concluída com atraso')
        self.assertEqual(action_state(action | {'due': ''}, '2026-10-13'), 'Aberta sem prazo')

    def test_versions_idempotence_and_failed_import_preserves_data(self):
        first = self.upload(export([{}])).json
        again = self.upload(export([{}])).json
        self.assertEqual(first['id'], again['id'])
        self.assertTrue(again['unchanged'])
        second = self.upload(export([{'Nota': '200'}])).json
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.upload(b'bad').status_code, 400)
        current = self.client.get('/api/failures/data').json
        self.assertEqual(len(current['history']), 2)
        self.assertEqual(current['notes'][0]['id'], '200')
        old = self.client.get('/api/failures/data?snapshot='+str(first['id'])).json
        self.assertEqual(old['notes'][0]['id'], '100')

    def test_meeting_persistence_scope_and_csrf(self):
        body = dict(line='023', month='2026-09', body='Revisar ronda. Responsável: equipe. Prazo: 20/10.')
        self.assertEqual(self.client.post('/api/failures/meeting', json=body).status_code, 403)
        self.assertEqual(self.client.post('/api/failures/meeting', json=body, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/failures/meeting?line=023&month=2026-09').json['body'], body['body'])
        self.assertEqual(self.client.get('/api/failures/meeting?line=010&month=2026-09').json['body'], '')
        self.assertEqual(self.client.get('/api/failures/meeting?line=023&month=2026-13').status_code, 400)

    def test_local_source_and_empty_state(self):
        self.assertEqual(self.client.get('/api/failures/data').json['notes'], [])
        self.assertEqual(self.client.post('/api/failures/import', headers=self.headers).status_code, 400)
        (self.root / 'ZPMX0072.xls').write_bytes(export([{}]))
        self.assertEqual(self.client.post('/api/failures/import', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/failures/data').json['notes'][0]['analysis_state'], 'Falha analisada')


if __name__ == '__main__':
    unittest.main()
