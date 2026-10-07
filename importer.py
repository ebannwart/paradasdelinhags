"""Import Excel without modifying source workbooks; match by semantic content."""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta

import openpyxl
from database import ACTIVE, connect, normalize

ALIASES = {
    'equipment': ['equipto', 'equipamento'], 'start': ['dt. inicio', 'data inicio'],
    'end': ['dt. fim', 'data fim'], 'minutes': ['tempo parada calculada'],
    'responsible_original': ['desc. un. resp.'], 'reason': ['desc. motivo parada'],
    'observation': ['observacao'], 'team': ['equipe'], 'shift': ['turno'],
}
REQUIRED = {'equipment', 'start', 'end', 'minutes', 'responsible_original', 'reason', 'observation'}
TYPES = ['Demais paradas', 'Manutenção Preventiva', 'Reparo Geral']


def clean_text(value):
    return '' if value is None else str(value).strip()


def responsible_group(value):
    text = normalize(value)
    code = text.split('-')[0].strip()
    # Names take precedence: in these exports ME means manutenção elétrica, MM mecânica.
    if 'mecan' in text: return 'Mecânica'
    if 'eletri' in text: return 'Elétrica'
    if code == 'mm': return 'Mecânica'
    if code in ('me', 'el'): return 'Elétrica'
    if 'opera' in text or code == 'op': return 'Operação'
    if 'setup' in text or 'set up' in text or code == 'su': return 'Setup'
    if 'programa' in text or code == 'pr': return 'Programação'
    if any(x in text for x in ('extern', 'processo anterior', 'materia prima')) or code in ('pa', 'ex'):
        return 'Externa'
    return clean_text(value) or 'Não informado'


def classify_type(reason, observation):
    text = normalize(reason + ' ' + observation)
    if re.search(r'\breparo\s+geral\b|\breforma\s+geral\b|\brg\b', text): return TYPES[2]
    if re.search(r'\bmp\b|\bmanutencao\s+preventiva\b|\bpreventiva\b', text): return TYPES[1]
    return TYPES[0]


def parse_date(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = None
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                result = datetime.strptime(value.strip(), fmt)
                break
            except ValueError:
                pass
        if result is None: raise ValueError('Data não reconhecida')
    else:
        raise ValueError('Data ausente ou inválida')
    # Excel often contains 59.999 instead of the next whole second.
    result = (result + timedelta(microseconds=500000)).replace(microsecond=0)
    if not 1900 <= result.year <= 2200: raise ValueError('Ano fora do intervalo esperado')
    return result.isoformat(timespec='seconds')


def header_map(row):
    names = [re.sub(r'\s*\(pe\)', '', normalize(x)).strip() for x in row]
    return {key: next((i for i, name in enumerate(names) if name in aliases), None)
            for key, aliases in ALIASES.items()}


def read_workbook(path):
    records, issues, invalid = [], [], 0
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    matched = 0
    try:
        for sheet in workbook:
            mapping = None
            for number, values in enumerate(sheet.iter_rows(values_only=True), 1):
                if mapping is None:
                    candidate = header_map(values)
                    if all(candidate[key] is not None for key in REQUIRED):
                        mapping = candidate
                        matched += 1
                    elif number >= 20:
                        break
                    continue
                if not any(v is not None for v in values): continue
                try:
                    raw = {k: values[i] if i is not None and i < len(values) else None
                           for k, i in mapping.items()}
                    row = {k: clean_text(v) for k, v in raw.items()}
                    row['start'], row['end'] = parse_date(raw['start']), parse_date(raw['end'])
                    if row['end'] < row['start']: raise ValueError('Fim anterior ao início')
                    if not row['equipment']: raise ValueError('Equipamento ausente')
                    try:
                        minutes = float(str(raw['minutes']).replace(',', '.'))
                    except (ValueError, TypeError):
                        raise ValueError('Tempo de parada ausente ou não numérico') from None
                    if not math.isfinite(minutes) or minutes < 0: raise ValueError('Minutos inválidos')
                    row['minutes'] = minutes
                    # Include all business fields, independent of file, row order and user tags.
                    row['id'] = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    row['responsible'] = responsible_group(row['responsible_original'])
                    row['auto_type'] = classify_type(row['reason'], row['observation'])
                    row['search_text'] = normalize(row['reason'] + ' ' + row['observation'])
                    row['sheet'], row['row_number'] = sheet.title, number
                    records.append(row)
                except (ValueError, TypeError, OverflowError) as exc:
                    invalid += 1
                    if len(issues) < 2000:
                        issues.append({'sheet': sheet.title, 'row': number, 'error': str(exc)})
            if mapping is None:
                issues.append({'sheet': sheet.title, 'row': 1, 'error': 'Aba ignorada: cabeçalhos obrigatórios não encontrados nas primeiras 20 linhas.'})
    finally:
        workbook.close()
    if not matched: raise ValueError('Nenhuma aba possui as colunas obrigatórias de paradas.')
    if not records: raise ValueError('Nenhum lançamento válido encontrado. A importação anterior foi preservada.')
    return records, invalid, issues


def rebuild_events(db, tolerance=None):
    if tolerance is None:
        tolerance = int(db.execute("SELECT value FROM settings WHERE key='tolerance_seconds'").fetchone()[0])
    rows = db.execute(f'SELECT r.id, r.equipment, r.start, r.end FROM records r WHERE {ACTIVE} ORDER BY equipment,start,end,id').fetchall()
    updates = []
    equipment = event_id = None
    frontier = None
    frontier_id = None
    overlaps = set()
    for row in rows:
        start, end = datetime.fromisoformat(row['start']), datetime.fromisoformat(row['end'])
        if row['equipment'] != equipment or start > frontier + timedelta(seconds=tolerance):
            equipment, event_id, frontier, frontier_id = row['equipment'], row['id'], end, row['id']
        else:
            if start < frontier:
                overlaps.update((row['id'], frontier_id))
            if end > frontier:
                frontier, frontier_id = end, row['id']
        updates.append((event_id, row['id']))
    db.execute('UPDATE records SET overlap=0')
    db.executemany('UPDATE records SET event_id=? WHERE id=?', updates)
    db.executemany('UPDATE records SET overlap=1 WHERE id=?', [(key,) for key in overlaps])


def import_file(db_path, path, name=None, rebuild=True):
    name = name or path.name
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    with connect(db_path) as db:
        old = db.execute('SELECT * FROM files WHERE name=?', (name,)).fetchone()
        if old and old['sha256'] == checksum:
            return {'name': name, 'status': 'unchanged', 'rows': old['row_count'], 'duplicates': old['duplicate_count'], 'invalid': old['invalid_count']}
    rows, invalid, issues = read_workbook(path)
    keys = ('id', 'equipment', 'start', 'end', 'minutes', 'responsible', 'responsible_original',
            'reason', 'observation', 'team', 'shift', 'search_text', 'auto_type')
    with connect(db_path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing = {r[0] for r in db.execute(f'SELECT r.id FROM records r WHERE {ACTIVE}')}
        # Duplicate counts describe this import, but data is deduplicated globally.
        seen = set()
        duplicates = 0
        other = {r[0] for r in db.execute('SELECT DISTINCT record_id FROM sources WHERE file_id != ?', (old['id'] if old else -1,))}
        for row in rows:
            duplicates += int(row['id'] in seen or row['id'] in other)
            seen.add(row['id'])
        dates = [r['start'] for r in rows]
        db.execute('''INSERT INTO files(name,sha256,imported_at,row_count,duplicate_count,invalid_count,min_date,max_date,issues)
                      VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET sha256=excluded.sha256,
                      imported_at=excluded.imported_at,row_count=excluded.row_count,duplicate_count=excluded.duplicate_count,
                      invalid_count=excluded.invalid_count,min_date=excluded.min_date,max_date=excluded.max_date,issues=excluded.issues''',
                   (name, checksum, datetime.now().isoformat(timespec='seconds'), len(rows), duplicates, invalid, min(dates), max(dates), json.dumps(issues, ensure_ascii=False)))
        file_id = db.execute('SELECT id FROM files WHERE name=?', (name,)).fetchone()[0]
        db.execute('DELETE FROM sources WHERE file_id=?', (file_id,))
        db.executemany(f"INSERT OR IGNORE INTO records({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",
                       [tuple(r[k] for k in keys) for r in rows])
        db.executemany('INSERT INTO sources VALUES(?,?,?,?)', [(file_id, r['sheet'], r['row_number'], r['id']) for r in rows])
        if rebuild: rebuild_events(db)
    return {'name': name, 'status': 'imported', 'rows': len(rows), 'duplicates': duplicates, 'invalid': invalid, 'new_records': len(seen - existing)}
