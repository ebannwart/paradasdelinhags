import calendar
import math
from datetime import date, timedelta

from database import ACTIVE, TYPE, normalize
from importer import TYPES
from modalities import MODALITIES, MODALITY_SQL


def values(filters, key):
    value = filters.get(key, [])
    if value in (None, ''): return []
    return value if isinstance(value, list) else [value]


def where(filters):
    clauses, args = [ACTIVE], []
    for key, column in [('equipment', 'r.equipment'), ('responsible', 'r.responsible'),
                        ('modality', MODALITY_SQL),
                        ('year', "substr(r.start,1,4)"), ('month', "substr(r.start,6,2)"),
                        ('day', "substr(r.start,9,2)"), ('type', TYPE)]:
        items = values(filters, key)
        if not items: continue
        if key in ('year', 'month', 'day'):
            limits = {'year': (1900,2200), 'month':(1,12), 'day':(1,31)}
            converted = [int(x) for x in items]
            if any(not limits[key][0] <= n <= limits[key][1] for n in converted):
                raise ValueError('Filtro de data inválido.')
            items = [str(n).zfill(4 if key == 'year' else 2) for n in converted]
        if key == 'type' and any(v not in TYPES for v in items): raise ValueError('Tipo de parada inválido.')
        if key == 'modality' and any(v not in MODALITIES for v in items): raise ValueError('Modalidade inválida.')
        clauses.append(f"{column} IN ({','.join('?' for _ in items)})")
        args.extend(items)
    files = values(filters, 'files')
    if files:
        files = [int(x) for x in files]
        clauses.append(f"EXISTS(SELECT 1 FROM sources sf WHERE sf.record_id=r.id AND sf.file_id IN ({','.join('?' for _ in files)}))")
        args.extend(files)
    offenders = values(filters, 'offender')
    if offenders:
        parts = []
        ids = [int(x) for x in offenders if str(x) != 'none']
        if ids:
            parts.append(f"r.offender_id IN ({','.join('?' for _ in ids)})")
            args.extend(ids)
        if 'none' in offenders: parts.append('r.offender_id IS NULL')
        clauses.append('(' + ' OR '.join(parts) + ')')
    for key, op in [('date_from', '>='), ('date_to', '<')]:
        if filters.get(key):
            day = date.fromisoformat(str(filters[key]))
            if key == 'date_to': day += timedelta(days=1)
            clauses.append(f'r.start {op} ?')
            args.append(day.isoformat())
    if filters.get('date_from') and filters.get('date_to') and filters['date_from'] > filters['date_to']:
        raise ValueError('A data inicial deve ser anterior à data final.')
    for key, op in [('min_minutes', '>='), ('max_minutes', '<=')]:
        if filters.get(key) not in (None, ''):
            number = float(filters[key])
            if not math.isfinite(number) or number < 0: raise ValueError('Duração inválida.')
            clauses.append(f'r.minutes {op} ?')
            args.append(number)
    if filters.get('min_minutes') not in (None, '') and filters.get('max_minutes') not in (None, ''):
        if float(filters['min_minutes']) > float(filters['max_minutes']): raise ValueError('Duração mínima maior que a máxima.')
    for word in normalize(filters.get('text', '')).split():
        clauses.append("r.search_text LIKE ? ESCAPE '\\'")
        args.append('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    if filters.get('overlap'): clauses.append('r.overlap=1')
    return ' AND '.join(clauses), args


def summary(db, filters):
    condition, params = where(filters)
    # Filter once: repeatedly walking the original wide Excel records and source
    # index is expensive on a multi-year database, particularly on Windows.
    db.execute('DROP TABLE IF EXISTS temp.analysis_rows')
    db.execute(f'''CREATE TEMP TABLE analysis_rows AS SELECT r.start,r.end,r.minutes,
        r.offender_id,r.event_id,r.overlap,r.responsible,r.equipment,{MODALITY_SQL} modality
        FROM records r WHERE {condition}''', params)
    condition, params = '1=1', []
    totals = dict(db.execute(f'''SELECT COUNT(*) records, COUNT(DISTINCT r.event_id) events,
        COALESCE(SUM(r.minutes),0) minutes, COALESCE(SUM(CASE WHEN r.offender_id IS NULL THEN r.minutes ELSE 0 END),0) unclassified_minutes,
        COALESCE(SUM(r.offender_id IS NULL),0) unclassified_records, COALESCE(SUM(r.overlap),0) overlaps,
        MIN(r.start) first_date, MAX(r.end) last_date FROM analysis_rows r WHERE {condition}''', params).fetchone())
    months = [dict(r) for r in db.execute(f'''SELECT substr(r.start,1,7) period, SUM(r.minutes) minutes,
        COUNT(*) records, COUNT(DISTINCT r.event_id) events FROM analysis_rows r WHERE {condition} GROUP BY period ORDER BY period''', params)]
    groups = {}
    for key, column, label in [('responsible', 'r.responsible', 'r.responsible'),
                              ('modality', 'r.modality', 'r.modality'),
                              ('equipment', 'r.equipment', 'r.equipment'),
                              ('offender', "COALESCE(CAST(r.offender_id AS TEXT),'none')", "COALESCE(o.name,'Não classificado')")]:
        groups[key] = [dict(r) for r in db.execute(f'''SELECT {column} key, {label} name,
            SUM(r.minutes) minutes, COUNT(*) records, COUNT(DISTINCT r.event_id) events
            FROM analysis_rows r LEFT JOIN offenders o ON o.id=r.offender_id WHERE {condition}
            GROUP BY {column} ORDER BY minutes DESC''', params)]
    dimension = 'offender' if filters.get('stack') == 'offender' else 'modality'
    stack_col = "COALESCE(CAST(r.offender_id AS TEXT),'none')" if dimension == 'offender' else 'r.modality'
    stack_name = "COALESCE(o.name,'Não classificado')" if dimension == 'offender' else 'r.modality'
    stacks = [dict(r) for r in db.execute(f'''SELECT substr(r.start,1,7) period, {stack_col} key,
        {stack_name} name, SUM(r.minutes) minutes FROM analysis_rows r LEFT JOIN offenders o ON o.id=r.offender_id
        WHERE {condition} GROUP BY period,{stack_col} ORDER BY period''', params)]
    offender_months = [dict(r) for r in db.execute('''SELECT substr(r.start,1,7) period,
        COALESCE(CAST(r.offender_id AS TEXT),'none') key, SUM(r.minutes) minutes,
        COUNT(DISTINCT r.event_id) events FROM analysis_rows r
        GROUP BY period,r.offender_id ORDER BY period''')]
    offender_years = [dict(r) for r in db.execute('''SELECT substr(r.start,1,4) period,
        COALESCE(CAST(r.offender_id AS TEXT),'none') key, SUM(r.minutes) minutes,
        COUNT(DISTINCT r.event_id) events FROM analysis_rows r
        GROUP BY period,r.offender_id ORDER BY period''')]
    # Presence in a source is evidence of records, not proof of a full operating calendar.
    coverage_filters = {k: v for k, v in filters.items() if k in ('files', 'year', 'month', 'day', 'date_from', 'date_to')}
    coverage_where, coverage_args = where(coverage_filters)
    coverage = [dict(r) for r in db.execute(f'''SELECT substr(r.start,1,7) period, MIN(r.start) first_date,
        MAX(r.start) last_date FROM records r WHERE {coverage_where} GROUP BY period ORDER BY period''', coverage_args)]
    selected_years = [int(y) for y in values(filters, 'year')]
    if not selected_years:
        selected_years = sorted({int(r['period'][:4]) for r in coverage})
    periods = []
    selected_months = [int(m) for m in values(filters, 'month')] or list(range(1,13))
    for year in selected_years:
        for month in sorted(selected_months):
            start, end = date(year,month,1).isoformat(), date(year,month,calendar.monthrange(year,month)[1]).isoformat()
            if filters.get('date_from') and end < filters['date_from']: continue
            if filters.get('date_to') and start > filters['date_to']: continue
            periods.append(f'{year:04d}-{month:02d}')
    return {'totals': totals, 'months': months, 'groups': groups, 'stacks': stacks, 'offender_months': offender_months,
            'coverage': coverage, 'periods': periods, 'stack': dimension, 'offender_years': offender_years}


def records(db, filters, page=1, page_size=50):
    condition, params = where(filters)
    total = db.execute(f'SELECT COUNT(*) FROM records r WHERE {condition}', params).fetchone()[0]
    page = max(1, min(page, max(1, math.ceil(total/page_size))))
    rows = [dict(r) for r in db.execute(f'''SELECT r.*, {TYPE} stop_type, {MODALITY_SQL} modality, o.name offender_name
        FROM records r LEFT JOIN offenders o ON o.id=r.offender_id WHERE {condition}
        ORDER BY r.start DESC,r.id LIMIT ? OFFSET ?''', params + [page_size,(page-1)*page_size])]
    return {'rows': rows, 'total': total, 'page': page, 'pages': max(1, math.ceil(total/page_size))}
