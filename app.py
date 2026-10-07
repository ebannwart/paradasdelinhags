import csv
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session
from plotly.offline import get_plotlyjs
from werkzeug.exceptions import HTTPException

import analytics
import maintenance
from modalities import MODALITIES, LABELS, MODALITY_SQL
from database import ACTIVE, TYPE, connect, initialize, normalize
from importer import TYPES, import_file, rebuild_events

ROOT = Path(__file__).resolve().parent


def create_app(db_path=None, source_dir=None):
    app = Flask(__name__)
    data_dir = ROOT / 'data'
    data_dir.mkdir(exist_ok=True)
    secret_file = data_dir / '.secret'
    if not secret_file.exists(): secret_file.write_text(secrets.token_hex(32))
    app.config.update(SECRET_KEY=secret_file.read_text().strip(), MAX_CONTENT_LENGTH=100 * 1024 * 1024,
                      SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_HTTPONLY=True,
                      DB_PATH=str(db_path or data_dir / 'paradas.sqlite3'), SOURCE_DIR=Path(source_dir or ROOT))
    initialize(app.config['DB_PATH'])
    job_lock = threading.Lock()
    job = {'running': False, 'completed': 0, 'total': 0, 'current': '', 'results': []}
    job_state_lock = threading.Lock()

    def database(): return connect(app.config['DB_PATH'])

    @app.before_request
    def protect_local_writes():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected = session.get('csrf', '')
            if not expected or not secrets.compare_digest(expected, request.headers.get('X-CSRF-Token', '')):
                return jsonify(error='Sessão expirada. Atualize a página e tente novamente.'), 403

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, (ValueError, TypeError)):
            return jsonify(error=str(exc) or 'Dados inválidos.'), 400
        if isinstance(exc, HTTPException): return jsonify(error=exc.description), exc.code
        app.logger.exception('Falha na aplicação')
        return jsonify(error='Não foi possível concluir a operação. Consulte o log da aplicação.'), 500

    @app.get('/')
    @app.get('/kpi-manutencao')
    def index():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('index.html', csrf=session['csrf'])

    @app.get('/vendor/plotly.js')
    def plotly():
        return app.response_class(get_plotlyjs(), mimetype='application/javascript', headers={'Cache-Control': 'public, max-age=86400'})

    @app.get('/api/meta')
    def meta():
        with database() as db:
            db.execute('BEGIN')
            dimensions = db.execute(f'''SELECT DISTINCT r.equipment,r.responsible,substr(r.start,1,4) year
                                        FROM records r WHERE {ACTIVE}''').fetchall()
            result = {key: sorted({r[key] for r in dimensions}) for key in ('equipment','responsible','year')}
            result['files'] = [dict(r) for r in db.execute('SELECT id,name,row_count,duplicate_count,invalid_count,min_date,max_date,imported_at FROM files ORDER BY name')]
            result['offenders'] = [dict(r) | {'equipment': json.loads(r['equipment'])} for r in db.execute('SELECT * FROM offenders ORDER BY name')]
            result['tolerance'] = int(db.execute("SELECT value FROM settings WHERE key='tolerance_seconds'").fetchone()[0]) / 60
            result['types'] = TYPES
            result['modalities'] = MODALITIES
            result['modality_labels'] = LABELS
        result['local_files'] = sorted(p.name for p in app.config['SOURCE_DIR'].glob('*.xlsx') if not p.name.startswith('~$'))
        return jsonify(result)

    @app.post('/api/summary')
    def summary():
        with database() as db:
            db.execute('BEGIN')
            return jsonify(analytics.summary(db, request.get_json() or {}))

    @app.post('/api/records')
    def records():
        body = request.get_json() or {}
        with database() as db:
            db.execute('BEGIN')
            return jsonify(analytics.records(db, body.get('filters', {}), int(body.get('page',1))))

    @app.post('/api/maintenance')
    def maintenance_report():
        body=request.get_json() or {}
        with database() as db:
            db.execute('BEGIN')
            return jsonify(maintenance.report(db,body.get('equipment'),body.get('files',[])))

    @app.post('/api/maintenance/targets')
    def maintenance_targets():
        body=request.get_json() or {}
        with database() as db:
            return jsonify(targets=maintenance.save_targets(db,body.get('equipment'),body.get('targets')))

    @app.get('/api/records/<record_id>')
    def detail(record_id):
        with database() as db:
            db.execute('BEGIN')
            row = db.execute(f'SELECT r.*, {TYPE} stop_type, {MODALITY_SQL} modality, o.name offender_name FROM records r LEFT JOIN offenders o ON o.id=r.offender_id WHERE r.id=? AND {ACTIVE}', (record_id,)).fetchone()
            if not row: return jsonify(error='Lançamento não encontrado.'), 404
            sources = [dict(r) for r in db.execute('SELECT f.name,s.sheet,s.row_number FROM sources s JOIN files f ON f.id=s.file_id WHERE s.record_id=?', (record_id,))]
            event_rows = [dict(r) for r in db.execute(f'SELECT r.id,r.start,r.end,r.minutes,r.responsible,{MODALITY_SQL} modality,r.reason,o.name offender_name FROM records r LEFT JOIN offenders o ON o.id=r.offender_id WHERE r.event_id=? AND {ACTIVE} ORDER BY r.start,r.end', (row['event_id'],))]
        return jsonify(record=dict(row), sources=sources, event_rows=event_rows)

    @app.post('/api/offenders')
    def save_offender():
        body = request.get_json() or {}
        name = str(body.get('name','')).strip()
        if not name or len(name) > 120: raise ValueError('Informe um nome com até 120 caracteres.')
        description = str(body.get('description','')).strip()[:2000]
        color = str(body.get('color','#147d75'))
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): raise ValueError('Cor inválida.')
        equipment = body.get('equipment', [])
        if not isinstance(equipment,list) or not all(isinstance(x,str) for x in equipment): raise ValueError('Equipamentos inválidos.')
        key = normalize(name)
        with database() as db:
            duplicate = db.execute('SELECT id FROM offenders WHERE name_key=?', (key,)).fetchone()
            offender_id = int(body['id']) if body.get('id') else None
            if duplicate and duplicate[0] != offender_id: raise ValueError('Já existe um ofensor com esse nome.')
            fields = (name,key,description,json.dumps(equipment),color)
            if offender_id:
                if not db.execute('SELECT id FROM offenders WHERE id=?',(offender_id,)).fetchone(): raise ValueError('Ofensor não encontrado.')
                db.execute('UPDATE offenders SET name=?,name_key=?,description=?,equipment=?,color=? WHERE id=?', fields+(offender_id,))
            else:
                offender_id = db.execute('INSERT INTO offenders(name,name_key,description,equipment,color) VALUES(?,?,?,?,?)', fields).lastrowid
        return jsonify(id=offender_id)

    @app.post('/api/classify')
    def classify():
        body = request.get_json() or {}
        field = body.get('field', 'offender_id')
        if field not in ('offender_id', 'type_override'): raise ValueError('Campo inválido.')
        value = body.get('value')
        if field == 'type_override' and value is not None and value not in TYPES: raise ValueError('Tipo inválido.')
        with database() as db:
            if field == 'offender_id' and value is not None:
                value = int(value)
                if not db.execute('SELECT 1 FROM offenders WHERE id=?',(value,)).fetchone(): raise ValueError('Ofensor não encontrado.')
            if body.get('all_filtered'):
                condition, params = analytics.where(body.get('filters', {}))
            else:
                ids = body.get('ids', [])
                if not isinstance(ids,list) or not 1 <= len(ids) <= 500: raise ValueError('Selecione de 1 a 500 lançamentos ou todos os resultados filtrados.')
                condition = ACTIVE + f" AND r.id IN ({','.join('?' for _ in ids)})"
                params = ids
            db.execute('BEGIN IMMEDIATE')
            count = db.execute(f'SELECT COUNT(*) FROM records r WHERE {condition}', params).fetchone()[0]
            if body.get('expected_count') is not None and count != int(body['expected_count']):
                raise ValueError('Os resultados mudaram. Atualize a seleção antes de classificar.')
            db.execute(f'UPDATE records SET {field}=? WHERE id IN (SELECT r.id FROM records r WHERE {condition})', [value]+params)
        return jsonify(updated=count)

    @app.post('/api/settings')
    def settings():
        minutes = float((request.get_json() or {}).get('tolerance',1))
        if not 0 <= minutes <= 60: raise ValueError('Use uma tolerância de 0 a 60 minutos.')
        if not job_lock.acquire(blocking=False): return jsonify(error='Aguarde a importação terminar.'),409
        try:
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("UPDATE settings SET value=? WHERE key='tolerance_seconds'", (str(round(minutes*60)),))
                rebuild_events(db)
        finally:
            job_lock.release()
        return jsonify(ok=True)

    def start_import(items, temporary=None):
        if not items: raise ValueError('Selecione pelo menos um arquivo .xlsx.')
        if not job_lock.acquire(blocking=False):
            if temporary: temporary.cleanup()
            return jsonify(error='Já existe uma importação ou reagrupamento em andamento.'),409
        with job_state_lock:
            job.update(running=True,completed=0,total=len(items),current='',results=[])

        def worker():
            try:
                for path,name in items:
                    with job_state_lock: job['current'] = name
                    try:
                        result = import_file(app.config['DB_PATH'],path,name)
                    except Exception as exc:
                        app.logger.exception('Falha ao importar %s',name)
                        result = {'name':name,'status':'error','error':str(exc)}
                    with job_state_lock:
                        job['results'].append(result)
                        job['completed'] += 1
            finally:
                if temporary: temporary.cleanup()
                with job_state_lock: job.update(running=False,current='')
                job_lock.release()
        threading.Thread(target=worker,daemon=True).start()
        return jsonify(started=True),202

    @app.post('/api/import/local')
    def import_local():
        names = (request.get_json() or {}).get('names',[])
        available = {p.name:p for p in app.config['SOURCE_DIR'].glob('*.xlsx') if not p.name.startswith('~$')}
        if not isinstance(names,list) or any(n not in available for n in names): raise ValueError('Arquivo não disponível na pasta do projeto.')
        return start_import([(available[n],n) for n in dict.fromkeys(names)])

    @app.post('/api/import/upload')
    def import_upload():
        uploads = request.files.getlist('files')
        if not uploads: raise ValueError('Selecione arquivos Excel.')
        temp = tempfile.TemporaryDirectory()
        items, seen = [], set()
        try:
            for index,upload in enumerate(uploads):
                name = (upload.filename or '').replace('\\','/').split('/')[-1]
                if not name.lower().endswith('.xlsx') or name.startswith('~$'): raise ValueError('Selecione apenas arquivos .xlsx.')
                if name in seen: raise ValueError('Selecione apenas um arquivo de cada nome.')
                seen.add(name)
                target = Path(temp.name)/f'{index}.xlsx'
                upload.save(target)
                items.append((target,name))
            return start_import(items,temp)
        except Exception:
            temp.cleanup()
            raise

    @app.get('/api/import/status')
    def import_status():
        with job_state_lock: return jsonify(job)

    @app.get('/api/files/<int:file_id>/issues')
    def issues(file_id):
        with database() as db:
            row = db.execute('SELECT issues,invalid_count FROM files WHERE id=?',(file_id,)).fetchone()
            if not row: return jsonify(error='Arquivo não encontrado.'),404
            return jsonify(issues=json.loads(row['issues']),invalid=row['invalid_count'])

    @app.post('/api/export')
    def export():
        condition,params = analytics.where(request.get_json() or {})
        stream = io.StringIO(newline='')
        writer = csv.writer(stream,delimiter=';')
        writer.writerow(['Equipamento','Início','Fim','Minutos','Responsável','Responsável original','Motivo','Observação','Ofensor','Tipo','Evento','Sobreposição','Modalidade','Fontes'])
        def cell(value):
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')): return "'"+value
            return value
        with database() as db:
            rows = db.execute(f'''SELECT r.equipment,r.start,r.end,r.minutes,r.responsible,r.responsible_original,
                r.reason,r.observation,COALESCE(o.name,''),{TYPE},r.event_id,r.overlap,{MODALITY_SQL},
                (SELECT GROUP_CONCAT(f.name || ' / ' || s.sheet || ' / linha ' || s.row_number, ' | ')
                 FROM sources s JOIN files f ON f.id=s.file_id WHERE s.record_id=r.id)
                FROM records r LEFT JOIN offenders o ON o.id=r.offender_id WHERE {condition} ORDER BY r.start''',params)
            for row in rows:
                line = list(row)
                line[3] = str(line[3]).replace('.',',')
                writer.writerow([cell(v) for v in line])
        return send_file(io.BytesIO(stream.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='paradas_filtradas.csv')

    @app.get('/api/backup')
    def backup():
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'backup.sqlite3'
            with database() as source:
                destination = sqlite3.connect(target)
                try: source.backup(destination)
                finally: destination.close()
            contents = target.read_bytes()
        return send_file(io.BytesIO(contents),mimetype='application/vnd.sqlite3',as_attachment=True,
                         download_name=f'paradas_backup_{datetime.now():%Y%m%d_%H%M%S}.sqlite3')

    return app


if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('PARADAS_PORT','5000'))
    print(f'Paradas de Linha: http://127.0.0.1:{port}',flush=True)
    serve(create_app(),host='127.0.0.1',port=port,threads=6)
