"""Monthly failure follow-up from SAP ZPMX text exports, with immutable snapshots."""
import hashlib
import json
import math
import re
import secrets
from datetime import datetime, timezone, timedelta

from flask import jsonify, render_template, request, session
from database import connect, normalize


def now():
    return datetime.now(timezone(timedelta(hours=-3)))


def iso(value):
    if not value or value == '00.00.0000':
        return ''
    try:
        return datetime.strptime(value, '%d.%m.%Y').date().isoformat()
    except ValueError as exc:
        raise ValueError(f'Data inválida no ZPMX: {value}') from exc


def duration_value(value):
    if not value:
        return None
    result = float(value.replace('.', '').replace(',', '.'))
    if not math.isfinite(result) or result < 0:
        raise ValueError('Duração inválida.')
    return result


def parse_export(content):
    if not content.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError('Use a exportação ZPMX em texto Unicode (.xls ou .txt).')
    lines = content.decode('utf-16').splitlines()
    header_index = next((i for i, line in enumerate(lines[:20]) if 'Descrição da nota ZC' in line and '\tNota\t' in line), None)
    if header_index is None:
        raise ValueError('Cabeçalho ZPMX não encontrado.')
    headers = lines[header_index].split('\t')
    continuation = lines[header_index + 1].split('\t') if header_index + 1 < len(lines) and lines[header_index + 1].startswith('Texto\t') else []
    required = ['Nota', 'Descrição da nota ZC', 'Local de instalação', 'Unidade Operacional', 'Status da Nota', 'Dta. parada processo', 'Dur. parada Prod.', 'Texto das Medidas', 'Status Medida']
    if any(h not in headers for h in required):
        raise ValueError('A exportação não contém todos os campos obrigatórios.')
    notes, warnings = {}, []
    row_count = 0
    i = header_index + 1 + bool(continuation)
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        physical_row = i + 1
        values = [v.strip() for v in lines[i].split('\t')]
        a = {h: values[j] if j < len(values) else '' for j, h in enumerate(headers) if h}
        if not a.get('Nota', '').isdigit():
            raise ValueError(f'Linha {physical_row}: início de nota inválido.')
        b = {}
        if continuation:
            i += 1
            if i >= len(lines):
                raise ValueError('Exportação incompleta: falta a continuação da última nota.')
            vals = [v.strip() for v in lines[i].split('\t')]
            if len(vals) > 1 and vals[1].isdigit():
                raise ValueError(f'Linha {i + 1}: continuação ausente.')
            b = {h: vals[j] if j < len(vals) else '' for j, h in enumerate(continuation) if h}
        i += 1
        row_count += 1
        asset = a['Local de instalação']
        parts = asset.split('-')
        line_code = parts[4] if len(parts) >= 5 else ''
        unit = a['Unidade Operacional']
        if not line_code:
            line_code = unit.split(' - ')[0]
        if not line_code:
            raise ValueError(f'Nota {a["Nota"]}: linha não identificada.')
        if unit and not unit.startswith(line_code + ' - '):
            warnings.append(f'Nota {a["Nota"]}: unidade diverge do local de instalação.')
        duration = a['Dur. parada Prod.']
        try:
            duration = duration_value(duration)
            process_duration = duration_value(a.get('Dur. parada processo', ''))
        except ValueError as exc:
            raise ValueError(f'Nota {a["Nota"]}: duração inválida.') from exc
        base = dict(id=a['Nota'], description=a['Descrição da nota ZC'], asset=asset, line=line_code,
                    unit=unit or line_code, status=a['Status da Nota'], date=iso(a['Dta. parada processo']),
                    process_duration=process_duration, work_center=a.get('Cent. Trab. Resp.', ''),
                    production_loss=a.get('Perda de Produção') if 'Perda de Produção' in headers else None,
                    production_date=iso(a.get('Dta. parada Prod.', '')),
                    duration=duration, owner=a.get('Nome usuário resp.Nota', ''), reopened=a.get('Reabertura', ''))
        if not base['date']:
            raise ValueError(f'Nota {base["id"]}: data da parada ausente.')
        note = notes.setdefault(base['id'], dict(base, investigations=[], actions=[], sources=[]))
        if any(note[k] != base[k] for k in ('asset', 'line', 'date', 'duration', 'status', 'process_duration', 'work_center', 'production_loss', 'production_date')):
            raise ValueError(f'Nota {base["id"]}: dados de parada ou status divergentes entre linhas.')
        note['sources'].append(physical_row)
        inv = dict(item=a.get('Item', ''), symptom=a.get('Texto sintoma do dano', ''),
                   cause=b.get('Texto da Causa') or b.get('Causa provável', ''),
                   why=[b.get(f'Porque {n}', '') for n in range(1, 6)], order=b.get('Ordem', ''))
        if any([inv['symptom'], inv['cause'], inv['order'], *inv['why']]) and inv not in note['investigations']:
            note['investigations'].append(inv)
        if a['Texto das Medidas'] or b.get('Item Medida'):
            action = dict(item=b.get('Item Medida', ''), object_item=a.get('Item', ''),
                          text=a['Texto das Medidas'], owner=a.get('Nome responsável', ''),
                          owner_code=b.get('Resp. Medida', ''), start=iso(a.get('Data planejada medida(inicio)', '')),
                          due=iso(a.get('Data planejada medida(fim)', '')), completed=iso(a.get('Data conclusão Medida', '')),
                          status=a['Status Medida'], efficacy=a.get('Eficácia', ''),
                          efficacy_status=b.get('Status Verif. Eficácia', ''))
            if action not in note['actions']:
                note['actions'].append(action)
    if not notes:
        raise ValueError('O arquivo não contém ocorrências válidas.')
    for note in notes.values():
        keys = [(a['object_item'], a['item']) for a in note['actions'] if a['item']]
        if len(keys) != len(set(keys)):
            warnings.append(f'Nota {note["id"]}: número de medida reutilizado; ações distintas preservadas.')
    return dict(notes=list(notes.values()), warnings=list(dict.fromkeys(warnings)), rows=row_count,
                extended=bool(continuation), schema_version=2)


def action_state(action, today):
    status = normalize(action['status'])
    if status in ('concluida', 'conc. apos prazo'):
        late = status == 'conc. apos prazo' or bool(action['completed'] and action['due'] and action['completed'] > action['due'])
        return 'Concluída com atraso' if late else 'Concluída'
    if status == 'aberta':
        if not action['due']:
            return 'Aberta sem prazo'
        return 'Vencida' if action['due'] < today else 'Aberta no prazo'
    return 'Status não identificado'


def analysis_state(note):
    status = normalize(note['status'])
    if status.startswith('nao requer'):
        return 'Dispensada'
    if status == 'falha em analise':
        return 'Em análise'
    if status.startswith('analise de falha concluida'):
        return 'Concluída'
    if status.startswith('falha analisada'):
        return 'Falha analisada'
    return 'Não classificada'


def import_snapshot(db_path, content, name):
    parsed = parse_export(content)
    # A new parser version creates a new snapshot instead of changing old history.
    digest = hashlib.sha256(content + b'\0failure-schema-2').hexdigest()
    with connect(db_path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT id FROM failure_snapshots WHERE sha=?', (digest,)).fetchone()
        if existing:
            return dict(id=existing['id'], unchanged=True)
        ident = db.execute('INSERT INTO failure_snapshots(name,sha,imported_at,payload) VALUES(?,?,?,?)',
                           (name, digest, now().isoformat(), json.dumps(parsed, ensure_ascii=False))).lastrowid
    return dict(id=ident, unchanged=False)


def register(app):
    path = app.config['DB_PATH']
    with connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS failure_snapshots(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, sha TEXT UNIQUE NOT NULL,
            imported_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS failure_meetings(
            line TEXT NOT NULL, month TEXT NOT NULL, body TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY(line,month));
        ''')

    @app.get('/analises-de-falha')
    def failure_page():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('failure_analysis.html', csrf=session['csrf'])

    @app.post('/api/failures/import')
    def failure_import():
        upload = request.files.get('file')
        if upload:
            name = upload.filename.replace('\\', '/').split('/')[-1]
            content = upload.read()
        else:
            from configuration import read_sources
            from pathlib import Path
            configured = read_sources(path)['failure']
            if not configured: raise ValueError('Configure o endereço do ZPMX em Configurações.')
            source = Path(configured)
            if not source.is_file():
                raise ValueError(f'ZPMX não encontrado no endereço configurado: {source}')
            name, content = source.name, source.read_bytes()
        return jsonify(import_snapshot(path, content, name))

    @app.get('/api/failures/data')
    def failure_data():
        with connect(path) as db:
            history = [dict(r) for r in db.execute('SELECT id,name,imported_at FROM failure_snapshots ORDER BY id DESC')]
            selected = request.args.get('snapshot', type=int) or (history[0]['id'] if history else None)
            row = db.execute('SELECT payload FROM failure_snapshots WHERE id=?', (selected,)).fetchone()
        if selected and not row:
            return jsonify(error='Importação não encontrada.'), 404
        data = json.loads(row['payload']) if row else dict(notes=[], warnings=[], rows=0, extended=False)
        today = now().date().isoformat()
        for note in data['notes']:
            note['analysis_state'] = analysis_state(note)
            for action in note['actions']:
                action['state'] = action_state(action, today)
        from configuration import read_sources
        return jsonify(**data, history=history, selected=selected, today=today,
                       page_size=read_sources(path)['failure_page_size'])

    @app.route('/api/failures/meeting', methods=['GET', 'POST'])
    def failure_meeting():
        body = request.get_json() or {} if request.method == 'POST' else request.args
        line, month = str(body.get('line', '')), str(body.get('month', ''))
        if not re.fullmatch(r'\d{3}', line) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            raise ValueError('Selecione uma linha e um mês para registrar o acompanhamento.')
        with connect(path) as db:
            if request.method == 'POST':
                text = body.get('body', '')
                if not isinstance(text, str) or len(text) > 20000:
                    raise ValueError('O registro deve ter até 20.000 caracteres.')
                db.execute('INSERT INTO failure_meetings VALUES(?,?,?,?) ON CONFLICT(line,month) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at',
                           (line, month, text, now().isoformat()))
            row = db.execute('SELECT body,updated_at FROM failure_meetings WHERE line=? AND month=?', (line, month)).fetchone()
        return jsonify(dict(row) if row else dict(body='', updated_at=''))
