"""SAP snapshot import and conservative maintenance-plan reporting."""
import hashlib
import json
import re
import secrets
import threading
from pathlib import Path
from datetime import date, datetime

import openpyxl
from flask import jsonify, render_template, request, session, send_file
from database import connect, normalize


def text(value):
    return str(value).strip() if value is not None else ''


def day(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    value = text(value)
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return ''


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sap_rows(kind TEXT, id TEXT, payload TEXT, PRIMARY KEY(kind,id));
    CREATE TABLE IF NOT EXISTS sap_files(name TEXT PRIMARY KEY, kind TEXT, rows INTEGER, imported_at TEXT);
    CREATE TABLE IF NOT EXISTS sap_groups(id INTEGER PRIMARY KEY, name TEXT UNIQUE, assets TEXT);
    CREATE TABLE IF NOT EXISTS sap_config(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
    CREATE TABLE IF NOT EXISTS sap_source_choices(kind TEXT PRIMARY KEY, path TEXT NOT NULL);
    ''')

    if 'position' not in {r[1] for r in db.execute('PRAGMA table_info(sap_groups)')}:
        db.execute('ALTER TABLE sap_groups ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
    if 'visible' not in {r[1] for r in db.execute('PRAGMA table_info(sap_groups)')}:
        db.execute('ALTER TABLE sap_groups ADD COLUMN visible INTEGER NOT NULL DEFAULT 1')


FIELDS = {
    'asset': 'Loc.instalação', 'name': 'Denominação', 'order': 'Ordem',
    'description': 'Texto breve', 'plan': 'Plano manut.', 'item': 'Item manut.',
    'user_status': 'Status usuário', 'system_status': 'Status sistema',
    'planned': 'Data planejada', 'basic_start': 'Data-base iníc.',
    'basic_end': 'Data-base fim', 'actual_end': 'Dt.real fim',
    'type': 'Tipo de ordem', 'work_center': 'CenTrab respon.',
    'item_text': 'Texto item man.', 'functional': 'Sistema Funcional',
    'work_actual': 'Trabalho real', 'work_planned': 'Trabalho',
    'activity_type': 'Tipo ativid.PM', 'abc': 'Código ABC', 'condition': 'Texto',
    'last_order': 'Última ordem', 'cycle': 'Ciclo', 'unit': 'Unidade',
    'deleted': 'Marc.p/elimin.', 'base_end_time': 'Fim-base (hora)', 'scheduled_end_time': 'Hora fim'}


def read_export(path, kind):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in wb:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, ())
            labels = [normalize(v) for v in header]
            required = {'IH06': ['Loc.instalação', 'Denominação'],
                        'IP18': ['Item manut.', 'Plano manut.', 'Texto item man.'],
                        'IP24': ['Item manut.', 'Data planejada'],
                        'IW39': ['Ordem', 'Loc.instalação'],
                        'IW49N': ['Ordem', 'Texto breve']}[kind]
            if not all(normalize(v) in labels for v in required):
                continue  # Ignore pivot and cover sheets.
            indices = {k: labels.index(normalize(v)) for k, v in FIELDS.items() if normalize(v) in labels}
            for number, values in enumerate(rows, 2):
                row = {k: day(values[i]) if k in ('planned', 'basic_start', 'basic_end', 'actual_end') else text(values[i])
                       for k, i in indices.items()}
                if not row.get('asset') and row.get('functional'):
                    row['asset'] = row['functional'].split(' - ')[0].strip()
                if not (row.get('asset') or row.get('order') or row.get('item')):
                    continue
                row['source'] = f'{path.name} · {sheet.title} · linha {number}'
                row['raw_hash'] = hashlib.sha256(json.dumps([text(v) for v in values],ensure_ascii=False).encode()).hexdigest()
                yield row
            return
        raise ValueError(f'{path.name}: aba de dados com os cabeçalhos necessários não encontrada.')
    finally:
        wb.close()


def import_exports(db_path, directory, selected_files=None):
    files = [(p, p.name.split(' ')[0].upper()) for p in sorted(directory.glob('*.xlsx'))
             if p.name.split(' ')[0].upper() in ('IH06', 'IP18', 'IP24', 'IW39', 'IW49N')] if selected_files is None else selected_files
    if not files:
        raise ValueError('Nenhum arquivo IP18, IH06, IP24, IW39 ou IW49N encontrado na pasta data.')
    batches, counts, duplicates = {}, [], 0
    for path, kind in files:
        batch = batches.setdefault(kind, {})
        count = 0
        for row in read_export(path, kind):
            count += 1
            if kind == 'IH06': key = row['asset']
            elif kind == 'IP18': key = row['plan'] + '|' + row['item']
            elif kind == 'IW39': key = row['order']
            elif kind == 'IP24': key = '|'.join(row.get(k, '') for k in ('item', 'planned', 'order', 'asset'))
            else: key = row['raw_hash']
            if key in batch:
                if {k:v for k,v in batch[key].items() if k != 'source'} != {k:v for k,v in row.items() if k != 'source'}:
                    raise ValueError(f'Registros conflitantes em {kind}, chave {key}. Mantenha uma exportação por recorte antes de importar.')
                duplicates += 1
            batch[key] = row
        counts.append((str(path) if selected_files is not None else path.name, kind, count, datetime.now().isoformat(timespec='seconds')))
    with connect(db_path) as db:
        db.execute('BEGIN IMMEDIATE')
        for kind, batch in batches.items():
            db.execute('DELETE FROM sap_rows WHERE kind=?', (kind,))
            db.execute('DELETE FROM sap_files WHERE kind=?', (kind,))
            db.executemany('INSERT INTO sap_rows VALUES(?,?,?)', [(kind,k,json.dumps(v,ensure_ascii=False)) for k,v in batch.items()])
        db.executemany('INSERT INTO sap_files VALUES(?,?,?,?)', counts)
    return {'files': len(files), 'rows': {k:len(v) for k,v in batches.items()}, 'duplicates': duplicates}


DEFAULT_CONFIG = {'done_user': [], 'not_done_user': [], 'plan_manter': False, 'no_plan_extra': False}


def config(db):
    row = db.execute('SELECT payload FROM sap_config WHERE id=1').fetchone()
    return DEFAULT_CONFIG | (json.loads(row[0]) if row else {})


def execution(row, cfg):
    user = set(row.get('user_status', '').split())
    system = set(row.get('system_status', '').split())
    if row.get('deleted') or user.intersection(cfg['not_done_user']):
        return 'Não executado'
    if user.intersection(cfg['done_user']) or system.intersection({'CNF', 'CONF'}):
        return 'Executado'
    return 'Não executado'


def level_asset(asset):
    match = re.match(r'^(G-CSN-79-001-010-\d{3})(?:-|$)', asset or '')
    return match[1] if match else ''


def load_rows(db, kind):
    return [json.loads(r[0]) for r in db.execute('SELECT payload FROM sap_rows WHERE kind=?', (kind,))]


def master_assets(db):
    names = {r['asset']: r.get('name','') for r in load_rows(db,'IH06')}
    codes = {level_asset(r.get('asset','')) or r.get('asset','') for r in load_rows(db,'IP18')}
    return [{'asset':a, 'name':names.get(a) or a} for a in sorted(codes) if a]


def duration_hours(base_end, scheduled_end):
    def seconds(value):
        value = text(value)
        if value == '24:00:00': value = '00:00:00'
        if not re.fullmatch(r'\d{2}:\d{2}:\d{2}', value): return None
        h, m, sec = map(int, value.split(':'))
        if h > 23 or m > 59 or sec > 59: return None
        return h * 3600 + m * 60 + sec
    a, b = seconds(base_end), seconds(scheduled_end)
    return None if a is None or b is None else abs(a - b) / 3600


def totals(rows):
    done = sum(r['execution']=='Executado' for r in rows)
    orders = {r['order']:r for r in rows if r.get('order')}
    durations = [r['duration_hours'] for r in orders.values() if r.get('duration_hours') is not None]
    duration_done = sum(r['duration_hours'] for r in orders.values()
                        if r.get('duration_hours') is not None and r['execution'] == 'Executado')
    duration_pending = sum(r['duration_hours'] for r in orders.values()
                           if r.get('duration_hours') is not None and r['execution'] != 'Executado')
    return dict(duration_hours=round(sum(durations), 2) if durations else None,
                duration_done=round(duration_done, 2) if durations else None,
                duration_pending=round(duration_pending, 2) if durations else None,
                duration_orders=len(durations), duration_missing_orders=len(orders)-len(durations),
                planned=len(rows), done=done, pending=len(rows)-done,
                rate=round(done/len(rows)*100,1) if rows else None,
                plans=len({r.get('plan') for r in rows if r.get('plan')}))


def report(db, filters, *, all_rows=False):
    cfg = config(db)
    masters = load_rows(db,'IP18')
    orders = load_rows(db,'IW39')
    calls = load_rows(db,'IP24')
    by_item = {r['item']:r for r in masters}
    by_plan = {}
    for r in masters: by_plan.setdefault(r.get('plan'),[]).append(r)
    names = {r['asset']:r.get('name','') for r in load_rows(db,'IH06')}
    order_index = {r['order']:r for r in orders}
    linked_calls = {r['order']:r for r in calls if r.get('order')}
    occurrences, covered, linked_orders = [], set(), set()

    def master_for(row):
        item = row.get('item')
        if item:
            candidate = by_item.get(item)
            if candidate and (not row.get('plan') or candidate.get('plan') == row['plan']): return candidate
            return None
        candidates = by_plan.get(row.get('plan'),[])
        return candidates[0] if len(candidates)==1 else None

    def occurrence(master, order, call=None):
        call = call or {}
        row = dict(master)
        row.update(order=order.get('order') or call.get('order',''),
                   planned=call.get('planned') or order.get('basic_start',''),
                   date_source='IP24' if call.get('planned') else 'IW39 · início básico',
                   user_status=order.get('user_status',''), system_status=order.get('system_status',''),
                   actual_end=order.get('actual_end',''), deleted=order.get('deleted',''),
                   description=master.get('item_text',''), order_description=order.get('description',''),
                   order_source=order.get('source',''), schedule_source=call.get('source',''))
        row['asset_original'] = row.get('asset','')
        row['asset'] = level_asset(row['asset_original'])
        row['asset_name'] = names.get(row['asset']) or row['asset'] or names.get(row['asset_original'],row['asset_original']) or 'Local não informado'
        row['execution'] = execution(row,cfg)
        row['duration_hours'] = duration_hours(order.get('base_end_time'), order.get('scheduled_end_time'))
        for field in ('type', 'activity_type', 'work_center', 'asset', 'basic_start', 'basic_end', 'base_end_time', 'scheduled_end_time'):
            row['order_' + field] = order.get(field, '')
        row['id'] = '|'.join((master['item'],row['order'],row['planned']))
        return row

    for order in orders:
        master = master_for(order)
        if master:
            call = linked_calls.get(order['order'])
            if call and call.get('item') != master['item']: call = None
            occurrences.append(occurrence(master,order,call))
            covered.add(master['item']); linked_orders.add(order['order'])
    # Preserve dated obligations even when the corresponding order is absent from IW39.
    for call in calls:
        if call.get('order') in linked_orders: continue
        master = master_for(call)
        if master:
            occurrences.append(occurrence(master,order_index.get(call.get('order'),{}),call))
            covered.add(master['item'])
    undated = [occurrence(m,{}) for m in masters if m['item'] not in covered]
    undated.extend(r for r in occurrences if not r['planned'])
    occurrences = [r for r in occurrences if r['planned']]
    # Stable occurrence identity protects overlapping snapshots from double counting.
    occurrences = list({r['id']:r for r in occurrences}.values())
    selected = filters.get('assets',[])
    if not isinstance(selected,list) or not all(isinstance(a,str) for a in selected): raise ValueError('Ativos inválidos.')
    for key in ('date_from','date_to','day'):
        if filters.get(key): date.fromisoformat(filters[key])
    if filters.get('month'):
        datetime.strptime(filters['month'], '%Y-%m')
    for field in ('activity_type','work_center'):
        value = filters.get(field, [])
        if not isinstance(value,(str,list)) or (isinstance(value,list) and not all(isinstance(v,str) for v in value)):
            raise ValueError('Seleção inválida para tipo de atividade ou centro de trabalho.')
    if filters.get('date_from') and filters.get('date_to') and filters['date_from'] > filters['date_to']:
        raise ValueError('O início do período deve ser anterior ao fim.')
    groups = [dict(r)|{'assets':sorted({level_asset(a) or a for a in json.loads(r['assets']) if a})}
              for r in db.execute('SELECT * FROM sap_groups ORDER BY position, name')]
    chosen = None
    if filters.get('group'):
        chosen = next((g for g in groups if str(g['id'])==str(filters['group'])),None)
        if chosen is None: raise ValueError('Grupo não encontrado.')

    def within_assets(row, assets):
        original = row['asset_original']
        return any(original == a or original.startswith(a + '-') for a in assets)

    def matches(row, dated=True, all_assets=False):
        if not all_assets and "summary_asset" in filters and (row["asset"] or row["asset_original"]) != filters["summary_asset"]: return False
        if filters.get("plan") and row.get("plan", "").upper() != filters["plan"].upper(): return False
        if not all_assets and selected and not within_assets(row, selected): return False
        for field in ('type','activity_type','work_center','abc','condition'):
            value = filters.get(field)
            if value and row.get(field,'') not in (value if isinstance(value,list) else [value]): return False
        if not all_assets and filters.get('search') and normalize(filters['search']) not in normalize(row['asset_name']+' '+row['asset']): return False
        if filters.get('text') and normalize(filters['text']) not in normalize(row.get('condition','')+' '+row.get('description','')): return False
        if dated:
            if filters.get('date_from') and row['planned'] < filters['date_from']: return False
            if filters.get('date_to') and row['planned'] > filters['date_to']: return False
        return True

    base = [r for r in occurrences if matches(r)]
    group_totals = [dict(id=g['id'],name=g['name'],visible=bool(g['visible']),**totals([r for r in base if within_assets(r, g['assets'])])) for g in groups]
    result = [r for r in base if chosen is None or within_assets(r, chosen['assets'])]
    missing = [r for r in undated if matches(r,False) and (chosen is None or within_assets(r, chosen['assets']))]
    summary = totals(result)
    daily, monthly, per_asset, per_plan = {}, {}, {}, {}
    for r in result:
        daily.setdefault(r['planned'],[]).append(r)
        monthly.setdefault(r['planned'][:7],[]).append(r)
        per_asset.setdefault((r['asset'] or r['asset_original'],r['asset_name']),[]).append(r)
        per_plan.setdefault(r.get('plan',''),[]).append(r)
    if filters.get('execution'): result = [r for r in result if r['execution']==filters['execution']]
    if filters.get('day'): result = [r for r in result if r['planned']==filters['day']]
    if filters.get('month'): result = [r for r in result if r['planned'].startswith(filters['month']+'-')]
    result.sort(key=lambda r:(r['planned'],r['plan'],r['item']),reverse=True)
    page = max(1,int(filters.get('page',1)))
    return dict(totals=summary,all_assets_totals=totals([r for r in occurrences if matches(r, all_assets=True)]),total=len(result),pages=max(1,(len(result)+49)//50),rows=result if all_rows else result[(page-1)*50:page*50],
                groups=group_totals, daily=[dict(day=k,**totals(v)) for k,v in sorted(daily.items())],
                monthly=[dict(month=k,order_count=len({r['order'] for r in v if r.get('order')}),**totals(v)) for k,v in sorted(monthly.items())],
                by_asset=[dict(asset=k[0],name=k[1],direct_location=not bool(level_asset(k[0])),**totals(v)) for k,v in per_asset.items()],
                by_plan=[dict(plan=k, descriptions=sorted({r.get('description','') for r in v if r.get('description')}),
                              **totals(v)) for k,v in sorted(per_plan.items())],
                undated_count=len(missing),undated=missing if all_rows else missing[:200],
                master_count=len(masters),outside_master_orders=len(orders)-len(linked_orders))


def register(app, data_dir):
    with connect(app.config['DB_PATH']) as db: initialize(db)
    lock = threading.Lock()
    job = {'running':False, 'error':'', 'result':None}

    @app.get('/plano-manutencao')
    def sap_page():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('sap_plan.html', csrf=session['csrf'])

    @app.get('/api/sap/meta')
    def sap_meta():
        with connect(app.config['DB_PATH']) as db:
            assets = master_assets(db)
            masters = load_rows(db,'IP18')
            dimensions = {k:sorted({r.get(k,'') for r in masters if r.get(k)}) for k in ('type','activity_type','work_center','abc','condition')}
            files = [dict(r) for r in db.execute('SELECT * FROM sap_files ORDER BY kind')]
            groups = [dict(r) | {'assets':json.loads(r['assets'])} for r in db.execute('SELECT * FROM sap_groups ORDER BY position, name')]
            cfg = config(db)
        return jsonify(assets=assets,files=files,groups=groups,config=cfg,dimensions=dimensions,job=dict(job))

    @app.get('/api/sap/source-choices')
    def sap_source_choices():
        available = sorted(p.resolve() for p in data_dir.glob('*.xlsx') if not p.name.startswith('~$'))
        with connect(app.config['DB_PATH']) as db:
            saved = dict(db.execute('SELECT kind,path FROM sap_source_choices').fetchall())
        available = sorted(set(available) | {Path(p) for p in saved.values() if p and Path(p).is_file()})
        choices = {}
        for kind in ('IP18', 'IW39', 'IP24', 'IH06'):
            candidates = [p for p in available if p.name.split(' ')[0].upper() == kind]
            choices[kind] = saved.get(kind, str(candidates[0]) if len(candidates) == 1 else '')
        return jsonify(choices=choices, available=[str(p) for p in available], directory=str(data_dir.resolve()))

    @app.post('/api/sap/import')
    def sap_import():
        choices = (request.get_json() or {}).get('choices')
        if not isinstance(choices, dict) or set(choices) != {'IP18','IW39','IP24','IH06'}:
            raise ValueError('Selecione os arquivos das quatro fontes SAP; deixe em branco as fontes que não deseja atualizar.')
        selected_files, paths = [], {}
        for kind, value in choices.items():
            if not isinstance(value, str): raise ValueError('Caminho de arquivo inválido.')
            value = value.strip().strip('"')
            if not value:
                paths[kind] = ''
                continue
            path = Path(value).expanduser()
            if not path.is_absolute(): path = data_dir / path
            path = path.resolve()
            if path.suffix.lower() != '.xlsx' or path.name.startswith('~$') or not path.is_file():
                raise ValueError(f'{kind}: arquivo Excel não encontrado: {path}')
            if str(path) in paths.values(): raise ValueError('Escolha um arquivo diferente para cada transação.')
            paths[kind] = str(path)
            selected_files.append((path, kind))
        if not selected_files: raise ValueError('Selecione pelo menos um arquivo para atualizar.')
        if not lock.acquire(False): return jsonify(error='Importação em andamento.'),409
        try:
            with connect(app.config['DB_PATH']) as db:
                db.executemany('INSERT OR REPLACE INTO sap_source_choices VALUES(?,?)', paths.items())
        except Exception:
            lock.release()
            raise
        job.update(running=True,error='',result=None)
        def worker():
            try: job['result'] = import_exports(app.config['DB_PATH'], data_dir, selected_files)
            except Exception as exc:
                app.logger.exception('Importação SAP')
                job['error'] = str(exc)
            finally:
                job['running'] = False
                lock.release()
        threading.Thread(target=worker,daemon=True).start()
        return jsonify(started=True),202

    @app.post('/api/sap/report')
    def sap_report():
        with connect(app.config['DB_PATH']) as db:
            db.execute('BEGIN')
            return jsonify(report(db, request.get_json() or {}))

    @app.post('/api/sap/export-plans')
    def sap_export_plans():
        from sap_export import export_plans
        body = request.get_json() or {}
        filters = dict(body.get('filters') or {})
        for key in ('execution', 'day', 'month', 'page'): filters.pop(key, None)
        with connect(app.config['DB_PATH']) as db:
            db.execute('BEGIN')
            data = report(db, filters, all_rows=True)
        return send_file(export_plans(data, filters, body.get('plan_order')),
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='realizacao_por_plano.xlsx')

    @app.route('/api/sap/plan-detail', methods=['GET', 'POST'])
    def sap_plan_detail():
        body = (request.get_json() or {}) if request.method == 'POST' else request.args.to_dict()
        code = text(body.get('plan')).upper()
        if not code: return jsonify(error='Informe o código do plano.'), 400
        with connect(app.config['DB_PATH']) as db:
            db.execute('BEGIN')
            items = [r for r in load_rows(db, 'IP18') if r.get('plan', '').upper() == code]
            if not items: return jsonify(error='Plano não encontrado na IP18 importada.'), 404
            filters = dict(body, plan=code)
            for key in ('execution', 'day', 'month', 'page'): filters.pop(key, None)
            data = report(db, filters, all_rows=True)
            visible_items = {r['item'] for r in data['rows'] + data['undated']}
            items = [r for r in items if r['item'] in visible_items]
            return jsonify(plan=code, items=items, totals=data['totals'], rows=data['rows'], undated=data['undated'])

    @app.post('/api/sap/config')
    def sap_config():
        body = request.get_json() or {}
        cfg = {k:bool(body.get(k)) for k in ('plan_manter','no_plan_extra')}
        for key in ('done_user','not_done_user'):
            value = body.get(key, [])
            if not isinstance(value,list) or any(not isinstance(v,str) or not re.fullmatch(r'[A-Z0-9_.-]{1,12}',v) for v in value):
                raise ValueError('Informe códigos de status separados por espaços.')
            cfg[key] = value
        if set(cfg['done_user']) & set(cfg['not_done_user']): raise ValueError('Um status não pode significar realizada e não realizada ao mesmo tempo.')
        with connect(app.config['DB_PATH']) as db:
            db.execute('INSERT OR REPLACE INTO sap_config VALUES(1,?)', (json.dumps(cfg),))
        return jsonify(ok=True)

    @app.post('/api/sap/groups')
    def sap_groups():
        body = request.get_json() or {}
        name, assets = text(body.get('name')), body.get('assets',[])
        if not name or len(name)>120 or not isinstance(assets,list) or not assets or not all(isinstance(a,str) for a in assets):
            raise ValueError('Informe o nome do grupo e selecione seus ativos.')
        with connect(app.config['DB_PATH']) as db:
            known = {r['asset'] for r in master_assets(db)}
            if not set(assets) <= known: raise ValueError('Selecione locais disponíveis no cadastro IP18.')
            group_id = body.get('id')
            if group_id is not None:
                if not db.execute('SELECT id FROM sap_groups WHERE id=?', (group_id,)).fetchone():
                    raise ValueError('Agrupamento não encontrado.')
                duplicate = db.execute('SELECT id FROM sap_groups WHERE name=? AND id<>?', (name, group_id)).fetchone()
                if duplicate: raise ValueError('Já existe um agrupamento com esse nome.')
                db.execute('UPDATE sap_groups SET name=?,assets=? WHERE id=?', (name,json.dumps(sorted(set(assets))),group_id))
            else:
                db.execute('INSERT INTO sap_groups(name,assets,position) VALUES(?,?,(SELECT COALESCE(MAX(position),0)+1 FROM sap_groups)) ON CONFLICT(name) DO UPDATE SET assets=excluded.assets', (name,json.dumps(sorted(set(assets)))))
        return jsonify(ok=True)

    @app.post('/api/sap/groups/reorder')
    def sap_groups_reorder():
        ids = (request.get_json() or {}).get('ids')
        with connect(app.config['DB_PATH']) as db:
            db.execute('BEGIN IMMEDIATE')
            known = {r[0] for r in db.execute('SELECT id FROM sap_groups')}
            if not isinstance(ids, list) or any(type(i) is not int for i in ids) or len(ids) != len(known) or set(ids) != known:
                raise ValueError('A lista de agrupamentos mudou. Atualize a página.')
            db.executemany('UPDATE sap_groups SET position=? WHERE id=?', enumerate(ids))
        return jsonify(ok=True)

    @app.post('/api/sap/groups/delete')
    def sap_groups_delete():
        group_id = (request.get_json() or {}).get('id')
        with connect(app.config['DB_PATH']) as db:
            if not db.execute('SELECT id FROM sap_groups WHERE id=?', (group_id,)).fetchone():
                raise ValueError('Agrupamento não encontrado.')
            db.execute('DELETE FROM sap_groups WHERE id=?', (group_id,))
        return jsonify(ok=True)

    @app.post('/api/sap/groups/visibility')
    def sap_group_visibility():
        body = request.get_json() or {}
        if type(body.get('visible')) is not bool: raise ValueError('Informe se o agrupamento deve ser exibido.')
        with connect(app.config['DB_PATH']) as db:
            result = db.execute('UPDATE sap_groups SET visible=? WHERE id=?', (int(body['visible']),body.get('id')))
            if not result.rowcount: raise ValueError('Agrupamento não encontrado.')
        return jsonify(ok=True)
