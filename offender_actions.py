"""Confirmed offender/notification links; actions always read from SAP snapshots."""
import json
import re
from datetime import datetime, timedelta
from flask import jsonify, request
from database import ACTIVE, connect
from failure_analysis import action_state, analysis_state, now

# Only productive lines with an identified counterpart in the ZPMX unit list.
SAP_LINES = {'010':'LZG1', '021':'LCI1', '022':'LPR1', '023':'LSL1',
             '028':'LCT1G', '030':'LIN1', '041':'LBT2'}


def notes_with_history(db, linked_ids=()):
    snapshots = db.execute('SELECT id,name,imported_at,payload FROM failure_snapshots ORDER BY id DESC')
    latest = next(snapshots, None)
    if latest is None:
        return {}, None
    notes = {n['id']:dict(n, stale=False, source_imported_at=latest['imported_at'])
             for n in json.loads(latest['payload'])['notes']}
    missing = set(linked_ids) - notes.keys()
    for snapshot in snapshots:
        if not missing:
            break
        for n in json.loads(snapshot['payload'])['notes']:
            if n['id'] in missing:
                notes[n['id']] = dict(n, stale=True, source_imported_at=snapshot['imported_at'])
                missing.remove(n['id'])
    return notes, dict(id=latest['id'], name=latest['name'], imported_at=latest['imported_at'])


MAPPING_KEY = 'offender_location_mappings'


def location_mappings(db):
    saved = db.execute('SELECT value FROM settings WHERE key=?', (MAPPING_KEY,)).fetchone()
    if saved is not None:
        return json.loads(saved['value'])
    notes, _ = notes_with_history(db)
    defaults = {}
    for n in notes.values():
        prefix = '-'.join(n['asset'].upper().split('-')[:5])
        if n['line'] in SAP_LINES and prefix:
            defaults[prefix] = SAP_LINES[n['line']]
    return [dict(local=k, equipment=v) for k,v in sorted(defaults.items())]


def mapped_equipment(asset, mappings):
    asset = asset.strip().upper()
    for row in sorted(mappings, key=lambda r: len(r['local']), reverse=True):
        if asset == row['local'] or asset.startswith(row['local'] + '-'):
            return row['equipment']
    return ''


def matching_launches(note, records):
    if not note.get('time') or not note.get('equipment'):
        return []
    instant = datetime.fromisoformat(note['date'] + 'T' + note['time'])
    # SAP process duration is in decimal hours. Missing duration is a point,
    # never substitute production duration, which may describe another interval.
    end = instant + timedelta(hours=note.get('process_duration') or 0)
    return [r for r in records if r['equipment'] == note['equipment'] and
            datetime.fromisoformat(r['start']) <= end and
            instant <= datetime.fromisoformat(r['end'])]


def register(app):
    path = app.config['DB_PATH']
    with connect(path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS offender_failure_links (
            offender_id INTEGER NOT NULL REFERENCES offenders(id) ON DELETE CASCADE,
            note_id TEXT NOT NULL, confirmed_at TEXT NOT NULL,
            PRIMARY KEY(offender_id,note_id))''')

    @app.route('/api/offender-actions/mappings', methods=['GET', 'POST'])
    def offender_location_settings():
        with connect(path) as db:
            if request.method == 'POST':
                db.execute('BEGIN IMMEDIATE')
            equipment = sorted({r['equipment'] for r in db.execute(
                f'SELECT DISTINCT r.equipment FROM records r WHERE {ACTIVE}')})
            if request.method == 'POST':
                body = request.get_json() or {}
                rows = body.get('mappings') if isinstance(body, dict) else None
                if not isinstance(rows, list) or len(rows) > 1000:
                    raise ValueError('Informe uma lista com até 1000 locais.')
                cleaned, seen = [], set()
                existing_lines = {r['equipment'] for r in location_mappings(db)}
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get('local'), str):
                        raise ValueError('Informe o local de instalação.')
                    local = row['local'].strip().upper()
                    line = row.get('equipment')
                    if not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*', local) or len(local) > 160:
                        raise ValueError('Local inválido. Use letras, números e hífens entre os segmentos.')
                    if local in seen:
                        raise ValueError('Local repetido: ' + local)
                    if not isinstance(line, str) or line not in set(equipment) | existing_lines:
                        raise ValueError('Selecione uma linha de produção cadastrada.')
                    seen.add(local)
                    cleaned.append(dict(local=local, equipment=line))
                db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',
                           (MAPPING_KEY, json.dumps(cleaned)))
            mappings = location_mappings(db)
            notes, _ = notes_with_history(db)
            assets = sorted({n['asset'] for n in notes.values() if n['asset']})
            return jsonify(mappings=mappings, equipment=sorted(set(equipment) | {r['equipment'] for r in mappings}), assets=assets)

    @app.get('/api/offender-actions')
    def offender_actions_data():
        ident = request.args.get('offender', type=int)
        with connect(path) as db:
            offenders = [dict(r) for r in db.execute('SELECT id,name,equipment FROM offenders ORDER BY name')]
            for o in offenders:
                o['equipment'] = json.loads(o['equipment'])
            if ident is None:
                return jsonify(offenders=offenders, notes=[], snapshot=None)
            if not any(o['id']==ident for o in offenders):
                raise ValueError('Ofensor não encontrado.')
            links = {r['note_id']:r['confirmed_at'] for r in db.execute(
                'SELECT note_id,confirmed_at FROM offender_failure_links WHERE offender_id=?', (ident,))}
            notes, snapshot = notes_with_history(db, links)
            # Suggestions use classified launches, never merely the offender's configured lines.
            evidence = []
            for r in db.execute(f'''SELECT r.id,r.equipment,r.start,r.end,r.minutes,r.observation,r.reason
                    FROM records r WHERE r.offender_id=? AND {ACTIVE} ORDER BY r.start''', (ident,)):
                evidence.append(dict(r))
            mappings = location_mappings(db)
            today = now().date().isoformat()
            for n in notes.values():
                n['equipment'] = mapped_equipment(n['asset'], mappings)
                n['manual_linked'] = n['id'] in links
                n['confirmed_at'] = links.get(n['id'])
                n['evidence'] = matching_launches(n, evidence)
                n['automatic'] = bool(n['evidence']) and not n['stale']
                n['linked'] = n['automatic'] or n['manual_linked']
                n['suggested'] = False
                n['analysis_state'] = analysis_state(n)
                for a in n['actions']:
                    a['state'] = action_state(a, today)
            return jsonify(offenders=offenders, notes=list(notes.values()), snapshot=snapshot)

    @app.post('/api/offender-actions/link')
    def offender_actions_link():
        body = request.get_json() or {}
        ident = int(body.get('offender', 0))
        note_id = str(body.get('note', ''))
        linked = body.get('linked')
        if type(linked) is not bool:
            raise ValueError('Informe se o vínculo deve ser confirmado ou removido.')
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM offenders WHERE id=?', (ident,)).fetchone():
                raise ValueError('Ofensor não encontrado.')
            if linked:
                notes, _ = notes_with_history(db)
                if note_id not in notes:
                    raise ValueError('Nota ausente da última importação. Atualize a lista antes de vincular.')
                db.execute('INSERT OR IGNORE INTO offender_failure_links VALUES(?,?,?)', (ident,note_id,now().isoformat()))
            else:
                db.execute('DELETE FROM offender_failure_links WHERE offender_id=? AND note_id=?', (ident,note_id))
        return jsonify(ok=True)
