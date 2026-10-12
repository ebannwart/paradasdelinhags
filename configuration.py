"""Persistent file addressing shared by the operational modules."""
import json
import re
import secrets
from pathlib import Path

from flask import jsonify, render_template, request, session
from database import connect, ACTIVE

PLAN_KINDS = ('IH06', 'IP18', 'IP24', 'IW39', 'IW49N')


def read_sources(db_path):
    with connect(db_path) as db:
        row = db.execute("SELECT value FROM settings WHERE key='application_sources'").fetchone()
        result = json.loads(row['value']) if row else dict(stops=[], failure='', failure_page_size=15)
        result['plan'] = dict(db.execute('SELECT kind,path FROM sap_source_choices').fetchall())
    return result


def resolve_source(value, root):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Caminho de arquivo inválido.')
    value = value.strip().strip('"')
    if not value:
        return ''
    path = Path(value).expanduser()
    return str((path if path.is_absolute() else root / path).resolve())


def initialize_sources(app):
    root = app.config['SOURCE_DIR']
    directory = root / 'Importacao'
    if not directory.is_dir():
        directory = root
    files = [p for p in directory.glob('*') if p.is_file() and not p.name.startswith('~$')]
    with connect(app.config['DB_PATH']) as db:
        if not db.execute("SELECT 1 FROM settings WHERE key='application_sources'").fetchone():
            initial = dict(stops=[str(p.resolve()) for p in sorted(files) if re.fullmatch(r'\d{4}\.xlsx', p.name, re.I)],
                           failure=str((directory / 'ZPMX0072.xls').resolve()), failure_page_size=15)
            db.execute('INSERT INTO settings(key,value) VALUES(?,?)', ('application_sources', json.dumps(initial)))
            # Preserve explicitly selected paths. Relocate only missing files found by name.
            saved = dict(db.execute('SELECT kind,path FROM sap_source_choices').fetchall())
            for kind in PLAN_KINDS:
                value = saved.get(kind)
                if value is not None:
                    if value and not Path(value).is_file() and (directory / Path(value).name).is_file():
                        db.execute('UPDATE sap_source_choices SET path=? WHERE kind=?', (str((directory / Path(value).name).resolve()), kind))
                    continue
                candidates = [p for p in files if p.suffix.lower() == '.xlsx' and p.name.split(' ')[0].upper() == kind]
                if len(candidates) == 1:
                    db.execute('INSERT INTO sap_source_choices VALUES(?,?)', (kind, str(candidates[0].resolve())))


def register(app):
    initialize_sources(app)
    path = app.config['DB_PATH']

    @app.get('/configuracoes')
    def configuration_page():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('configuration.html', csrf=session['csrf'])

    @app.get('/api/configuration')
    def configuration_read():
        values = read_sources(path)
        root = app.config['SOURCE_DIR'] / 'Importacao'
        available = sorted(str(p.resolve()) for p in root.glob('*') if p.is_file() and p.suffix.lower() in ('.xls', '.xlsx', '.txt') and not p.name.startswith('~$'))
        paths = [*values['stops'], values['failure'], *values['plan'].values()]
        with connect(path) as db:
            tolerance = float(db.execute("SELECT value FROM settings WHERE key='tolerance_seconds'").fetchone()[0]) / 60
            equipment = [r[0] for r in db.execute(f'SELECT DISTINCT r.equipment FROM records r WHERE {ACTIVE} ORDER BY r.equipment')]
            targets = [dict(r) for r in db.execute('SELECT * FROM maintenance_targets')]
            files = [dict(r) for r in db.execute('SELECT name,row_count,imported_at FROM files ORDER BY name')]
        return jsonify(sources=values, available=available, directory=str(root.resolve()),
                       existence={p:Path(p).is_file() for p in paths if p}, tolerance=tolerance,
                       equipment=equipment, targets=targets, files=files)

    @app.post('/api/configuration/sources')
    def configuration_save():
        body = request.get_json() or {}
        section = body.get('section')
        root = app.config['SOURCE_DIR']
        if section == 'stops':
            values = body.get('paths')
            if not isinstance(values, list) or len(values) > 100:
                raise ValueError('Informe até 100 arquivos de paradas.')
            values = list(dict.fromkeys(resolve_source(p, root) for p in values if p))
            if any(Path(p).suffix.lower() != '.xlsx' for p in values):
                raise ValueError('As paradas devem usar arquivos .xlsx.')
            if len({Path(p).name.casefold() for p in values}) != len(values):
                raise ValueError('As fontes de paradas precisam ter nomes de arquivo diferentes.')
        elif section == 'failure':
            values = resolve_source(body.get('path', ''), root)
            if values and Path(values).suffix.lower() not in ('.xls', '.txt'):
                raise ValueError('Informe o ZPMX em .xls ou .txt Unicode.')
            size = body.get('page_size', 15)
            if type(size) is not int or size not in (15,25,50,100):
                raise ValueError('Escolha 15, 25, 50 ou 100 ocorrências por página.')
        elif section == 'plan':
            choices = body.get('choices')
            if not isinstance(choices, dict) or set(choices) != set(PLAN_KINDS):
                raise ValueError('Informe os endereços das cinco fontes SAP (campos opcionais podem ficar vazios).')
            values = {k:resolve_source(v, root) for k,v in choices.items()}
            nonempty = [v for v in values.values() if v]
            if any(Path(p).suffix.lower() != '.xlsx' for p in nonempty) or len(set(nonempty)) != len(nonempty):
                raise ValueError('Use arquivos .xlsx diferentes para cada transação.')
        else:
            raise ValueError('Seção inválida.')
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if section == 'plan':
                db.executemany('INSERT OR REPLACE INTO sap_source_choices VALUES(?,?)', values.items())
            else:
                saved = json.loads(db.execute("SELECT value FROM settings WHERE key='application_sources'").fetchone()[0])
                saved[section] = values
                if section == 'failure':
                    saved['failure_page_size'] = size
                db.execute("UPDATE settings SET value=? WHERE key='application_sources'", (json.dumps(saved),))
        return jsonify(ok=True)
