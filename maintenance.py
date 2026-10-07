"""Calendar-based maintenance indicators, with auditable period inputs."""
import calendar
import math
from datetime import datetime, timedelta

from database import ACTIVE
from modalities import MODALITIES, MODALITY_SQL

INDICATORS = ('imc', 'dgfm', 'mtbf', 'mttr', 'failure_events')


def next_month(value):
    return datetime(value.year + (value.month == 12), value.month % 12 + 1, 1)


def merge_windows(windows):
    merged = []
    for start,end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0],max(end,merged[-1][1]))
        else: merged.append((start,end))
    return merged


def period_bucket(period, windows):
    return {'period':period, 'windows':windows,
            'calendar_minutes':sum((b-a).total_seconds()/60 for a,b in windows),
            'modalities':{key:0.0 for key in MODALITIES},
            'events':set(), 'records':set(), 'overlaps':set(), 'zero_duration':set()}


def calculate(bucket):
    total=bucket['calendar_minutes'];counts=bucket['modalities']
    corrective=counts['ME']+counts['MM'];preventive=counts['Preventiva'];failures=len(bucket['events'])
    has_data=bool(bucket['records']) and total>0
    corrective_ok=has_data and corrective <= total + 1e-7
    maintenance_ok=has_data and corrective+preventive <= total + 1e-7
    errors=[]
    if not has_data: errors.append('Sem lançamentos da linha neste período; disponibilidade não presumida.')
    if has_data and not corrective_ok: errors.append('ME + MM excede o tempo calendário; confira os lançamentos e sobreposições.')
    if has_data and not maintenance_ok: errors.append('ME + MM + Preventiva excede o tempo calendário; DGFM indisponível.')
    return {'period':bucket['period'], 'calendar_minutes':total, 'calendar_hours':total/60,
            'modalities':counts, 'corrective_minutes':corrective, 'preventive_minutes':preventive,
            'failures':failures, 'records':len(bucket['records']), 'overlaps':len(bucket['overlaps']),
            'zero_duration':len(bucket['zero_duration']),
            'imc':corrective/total*100 if corrective_ok else None,
            'dgfm':(1-(corrective+preventive)/total)*100 if maintenance_ok else None,
            'mtbf':(total-corrective)/failures/60 if corrective_ok and failures else None,
            'mttr':corrective/failures if has_data and failures else None,
            'failure_events':failures if has_data else None,
            'errors':errors,
            'coverage': [{'from':a.date().isoformat(),'to':(b-timedelta(seconds=1)).date().isoformat()}
                         for a,b in bucket['windows']]}


def report(db, equipment, file_ids=None):
    if not equipment or not db.execute(f'SELECT 1 FROM records r WHERE r.equipment=? AND {ACTIVE} LIMIT 1',(equipment,)).fetchone():
        raise ValueError('Selecione uma linha importada.')
    file_ids=file_ids or []
    if not isinstance(file_ids,list): raise ValueError('Seleção de arquivos inválida.')
    file_ids=list(dict.fromkeys(int(x) for x in file_ids))
    file_where='1=1' if not file_ids else f"id IN ({','.join('?' for _ in file_ids)})"
    files=[dict(r) for r in db.execute(f'SELECT id,name,min_date,max_date FROM files WHERE {file_where} ORDER BY name',file_ids)]
    if file_ids and len(files)!=len(file_ids): raise ValueError('Arquivo selecionado não encontrado.')
    windows=merge_windows([(datetime.fromisoformat(f['min_date']).replace(hour=0,minute=0,second=0),
                            datetime.fromisoformat(f['max_date']).replace(hour=0,minute=0,second=0)+timedelta(days=1))
                           for f in files if f['min_date'] and f['max_date']])
    month_windows={}
    for start,end in windows:
        cursor=start.replace(day=1)
        while cursor<end:
            boundary=next_month(cursor)
            month_windows.setdefault(cursor.strftime('%Y-%m'),[]).append((max(start,cursor),min(end,boundary)))
            cursor=boundary
    buckets={p:period_bucket(p,parts) for p,parts in month_windows.items()}
    source_filter=ACTIVE
    params=[equipment]
    if file_ids:
        source_filter=f"EXISTS(SELECT 1 FROM sources s WHERE s.record_id=r.id AND s.file_id IN ({','.join('?' for _ in file_ids)}))"
        params+=file_ids
    rows=db.execute(f'''SELECT r.id,r.start,r.end,r.minutes,r.event_id,r.overlap,{MODALITY_SQL} modality
                        FROM records r WHERE r.equipment=? AND {source_filter} ORDER BY r.start''',params)
    outside_minutes=0.0
    for row in rows:
        start,end=datetime.fromisoformat(row['start']),datetime.fromisoformat(row['end'])
        duration=(end-start).total_seconds()
        cursor=start.replace(day=1,hour=0,minute=0,second=0)
        allocated=0.0
        while cursor<=end:
            boundary=next_month(cursor);period=cursor.strftime('%Y-%m');bucket=buckets.get(period)
            if bucket:
                portions=[]
                for left,right in bucket['windows']:
                    seconds=max(0,(min(end,right)-max(start,left)).total_seconds())
                    if seconds>0 or (duration==0 and left<=start<right): portions.append(seconds)
                if portions:
                    minutes=row['minutes']*sum(portions)/duration if duration>0 else row['minutes']
                    allocated+=minutes
                    bucket['modalities'][row['modality']]+=minutes
                    bucket['records'].add(row['id'])
                    if row['overlap']: bucket['overlaps'].add(row['id'])
                    if duration==0 and row['minutes']>0:bucket['zero_duration'].add(row['id'])
                    if row['modality'] in ('ME','MM') and minutes>0:
                        bucket['events'].add(row['event_id'] or row['id'])
            cursor=boundary
        outside_minutes+=max(0,row['minutes']-allocated)
    monthly={p:calculate(bucket) for p,bucket in sorted(buckets.items())}
    annual=[]
    for year in sorted({p[:4] for p in buckets}):
        source_months=[b for p,b in buckets.items() if p.startswith(year)]
        observed=[b for b in source_months if b['records']]
        combined=period_bucket(year,[window for b in observed for window in b['windows']])
        for b in observed:
            for key in MODALITIES: combined['modalities'][key]+=b['modalities'][key]
            for key in ('events','records','overlaps','zero_duration'): combined[key].update(b[key])
        item=calculate(combined)
        item['months_with_data']=len(observed)
        item['failure_events']=item['failures']/len(observed) if observed else None
        item['source_months']=len(source_months)
        full_calendar=(366 if calendar.isleap(int(year)) else 365)*1440
        item['partial']=abs(item['calendar_minutes']-full_calendar)>.01
        annual.append(item)
    latest_year=max((int(f['max_date'][:4]) for f in files if f['max_date']),default=None)
    latest_months=[]
    if latest_year:
        for month in range(1,13):
            period=f'{latest_year}-{month:02d}'
            item=monthly.get(period) or calculate(period_bucket(period,[]))
            item['month']=month
            item['partial']=0 < item['calendar_minutes'] < calendar.monthrange(latest_year,month)[1]*1440
            latest_months.append(item)
    targets={key:None for key in INDICATORS}
    targets.update({r['indicator']:r['value'] for r in db.execute('SELECT indicator,value FROM maintenance_targets WHERE equipment=?',(equipment,))})
    return {'equipment':equipment,'files':files,'annual':annual,'monthly':latest_months,'latest_year':latest_year,
            'targets':targets,'outside_minutes':outside_minutes,
            'tolerance_minutes':int(db.execute("SELECT value FROM settings WHERE key='tolerance_seconds'").fetchone()[0])/60}


def save_targets(db, equipment, targets):
    if not equipment or not db.execute(f'SELECT 1 FROM records r WHERE r.equipment=? AND {ACTIVE} LIMIT 1',(equipment,)).fetchone():
        raise ValueError('Selecione uma linha importada.')
    if not isinstance(targets,dict) or set(targets)!=set(INDICATORS):
        raise ValueError('Informe as metas de todos os indicadores. Use vazio para remover uma meta.')
    validated={}
    for indicator,value in targets.items():
        if value is None or value=='':validated[indicator]=None;continue
        value=float(value)
        if not math.isfinite(value) or value<0 or (indicator in ('imc','dgfm') and value>100):
            raise ValueError('Metas percentuais devem estar entre 0 e 100; tempos e quantidades devem ser positivos ou zero.')
        validated[indicator]=value
    db.execute('BEGIN IMMEDIATE')
    for indicator,value in validated.items():
        if value is None:db.execute('DELETE FROM maintenance_targets WHERE equipment=? AND indicator=?',(equipment,indicator))
        else:db.execute('''INSERT INTO maintenance_targets VALUES(?,?,?)
                          ON CONFLICT(equipment,indicator) DO UPDATE SET value=excluded.value''',(equipment,indicator,value))
    return validated
