'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number(v).toLocaleString('pt-BR');
const rate=v=>v===null?'—':num(v)+'%';
const dt=v=>v?v.split('-').reverse().join('/'):'—';
const planProfile=new URLSearchParams(location.search).get('profile')||'1';
let meta={},version=0,polling=false,calendarData=[];
let appliedPlanFilters=null,detailCode='',detailVersion=0;
let selectedSummaryAsset=null,summaryData=null,summaryVersion=0;
const summarySort={};
const summaryCollator=new Intl.Collator('pt-BR',{numeric:true,sensitivity:'base'});
function enableSummarySorting(id, rows, keys){
 const table=$(id).querySelector('table');if(!table)return;
 const entries=[...table.tBodies[0].rows].filter(r=>!r.classList.contains('inline-plan-detail')).map((element,i)=>({element,data:rows[i],index:i}));
 const headers=[...table.tHead.rows[0].cells];
 function apply(){
  const state=summarySort[id];
  headers.forEach((th,i)=>{th.setAttribute('aria-sort',state?.column===i?(state.desc?'descending':'ascending'):'none');th.querySelector('.sort-arrow').textContent=state?.column===i?(state.desc?'↓':'↑'):'↕';});
  if(!state)return;
  entries.sort((a,b)=>{
   const av=keys[state.column](a.data),bv=keys[state.column](b.data);
   if(av==null||bv==null)return av==null?(bv==null?a.index-b.index:1):-1;
   const comparison=typeof av==='number'&&typeof bv==='number'?av-bv:summaryCollator.compare(String(av),String(bv));
   return (state.desc?-comparison:comparison)||a.index-b.index;
  });
  table.tBodies[0].append(...entries.map(entry=>entry.element));
  const detail=table.querySelector(".inline-plan-detail"),selected=table.querySelector("tr[data-plan].selected");if(detail&&selected)selected.after(detail);
 }
 headers.forEach((th,column)=>{const label=th.textContent;th.scope='col';th.innerHTML=`<button type="button" class="summary-sort" title="Ordenar por ${esc(label)}">${esc(label)} <span class="sort-arrow" aria-hidden="true">↕</span></button>`;th.querySelector('button').onclick=()=>{const previous=summarySort[id];summarySort[id]={column,desc:previous?.column===column?!previous.desc:false};apply();};});
 apply();
}
function message(t,error=false){$('message').hidden=!t;$('message').textContent=t;$('message').className='notice'+(error?' warning':'');}
async function api(path,body){const r=await fetch('/api/sap/'+path+'?profile='+encodeURIComponent(planProfile),body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Falha na solicitação.');return data;}
function run(fn){return async e=>{if(e)e.preventDefault();try{await fn(e);}catch(err){message(err.message,true);}};}
function selected(){return [...$('assets').selectedOptions].map(x=>x.value);}
function filterAssets(){const keep=selected(),q=$('search').value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();$('assets').innerHTML=(meta.assets||[]).filter(a=>keep.includes(a.asset)||(a.asset+' '+a.name).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q)).map(a=>`<option value="${esc(a.asset)}" ${keep.includes(a.asset)?'selected':''}>${esc(a.name)} · ${esc(a.asset)}</option>`).join('');}
async function loadMeta(){meta=await api('meta');filterAssets();const group=$('group').value;$('group').innerHTML='<option value="">Todos os grupos</option>'+meta.groups.map(g=>`<option value="${g.id}">${esc(g.name)}</option>`).join('');$('group').value=group;$('done-user').value=meta.config.done_user.join(' ');$('not-done-user').value=meta.config.not_done_user.join(' ');for(const key of ['type','activity_type','work_center','abc','condition']){const old=[...$(key).selectedOptions].map(o=>o.value);$(key).innerHTML=($(key).multiple?'':'<option value="">Todos</option>')+(meta.dimensions[key]||[]).map(v=>`<option>${esc(v)}</option>`).join('');for(const option of $(key).options)option.selected=old.includes(option.value);}
$('sources').innerHTML=meta.files.length?meta.files.map(f=>`<p><b>${esc(f.name)}</b> · ${num(f.rows)} linhas · importado em ${esc(f.imported_at.replace('T',' '))}</p>`).join(''):'<p>Nenhuma fonte importada. Defina as fontes em Configurações e atualize o plano preventivo.</p>';
const warnings=['A IP18 é o cadastro mestre. A execução usa a IW39: sem confirmação final, a ocorrência conta como não executada.'];if(!meta.files.some(f=>f.kind==='IP18'))warnings.push('Importe a IP18 para carregar o cadastro mestre.');if(meta.files.some(f=>f.kind==='IP24'&&f.rows===5000))warnings.push('IP24 com 5.000 linhas: pode haver limite de exportação. Datas complementares vêm da IW39; a cobertura da programação depende dos arquivos importados.');$('limitations').textContent=warnings.join(' ');$('import').disabled=meta.job.running;
renderGroupManager();if(meta.job.running&&!polling)pollImport();}
const dateStorageKey='sap-plan-date-filter-'+planProfile;
function saveDateFilter(){
 try{localStorage.setItem(dateStorageKey,JSON.stringify({from:$('from').value,to:$('to').value}));}catch(error){/* Storage can be unavailable in private environments. */}
}
function restoreDateFilter(){
 try{const saved=JSON.parse(localStorage.getItem(dateStorageKey)||(planProfile==='1'?localStorage.getItem('sap-plan-date-filter'):null)||'null');if(!saved||typeof saved!=='object')return;
  for(const key of ['from','to'])if(typeof saved[key]==='string'&&(!saved[key]||/^\d{4}-\d{2}-\d{2}$/.test(saved[key])))$(key).value=saved[key];
 }catch(error){/* Ignore invalid or unavailable local storage. */}
}
function clearFiltersKeepingDates(){
 const from=$('from').value,to=$('to').value;$('filters').reset();$('from').value=from;$('to').value=to;saveDateFilter();
}
function filters(){return {date_from:$('from').value,date_to:$('to').value,assets:selected(),group:$('group').value,search:$('search').value,text:$('text').value,type:$('type').value,activity_type:[...$('activity_type').selectedOptions].map(o=>o.value),work_center:[...$('work_center').selectedOptions].map(o=>o.value),abc:$('abc').value,condition:$('condition').value,};}
function calendar(){
 const hours=$('chart-secondary').value==='hours',label=hours?'H Total':'Total de ordens',value=m=>hours?m.duration_hours:m.order_count,format=v=>v==null?'—':num(v);
 const index=m=>hours?(m.duration_hours>0&&m.duration_done!=null?Math.round(m.duration_done/m.duration_hours*1000)/10:null):m.rate;
 const indexLabel=hours?'Índice por horas':'Índice por quantidade';
 if(!calendarData.length){$('calendar').innerHTML='<p>Sem ocorrências no recorte selecionado.</p>';return;}
 const data=calendarData,w=Math.max(760,data.length*90+140),h=360,left=70,right=w-70,top=48,bottom=290;
 const step=Math.max(1,Math.ceil(Math.max(...data.map(m=>value(m)??0))/5)),maxOrders=step*5;
 const slot=(right-left)/data.length,x=i=>left+slot*(i+.5),yRate=v=>bottom-(bottom-top)*v/100,yOrders=v=>bottom-(bottom-top)*v/maxOrders;
 const grid=Array.from({length:6},(_,i)=>{const y=yRate(i*20);return `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" stroke="#dce5e8"/><text x="${left-12}" y="${y+4}" text-anchor="end">${i*20}%</text><text x="${right+12}" y="${y+4}">${num(i*step)}</text>`;}).join('');
 const bars=data.map((m,i)=>`<g><title>${esc(m.month)}: índice ${rate(index(m))}; ${format(value(m))} ${hours?'H':'ordens'}; ${hours?format(m.duration_done)+' H executadas de '+format(m.duration_hours)+' H previstas':num(m.done)+' executadas de '+num(m.planned)+' previstas'}</title><rect x="${x(i)-slot*.26}" y="${yRate(index(m)??0)}" width="${slot*.52}" height="${bottom-yRate(index(m)??0)}" rx="3" fill="#138477"/><text x="${x(i)}" y="${yRate(index(m)??0)-9}" text-anchor="middle" fill="#086458">${rate(index(m))}</text><text x="${x(i)}" y="${bottom+25}" text-anchor="middle">${esc(m.month.slice(5)+'/'+m.month.slice(0,4))}</text></g>`).join('');
 let connected=false;const points=data.map((m,i)=>{if(value(m)==null){connected=false;return '';}const point=`${connected?'L':'M'} ${x(i)} ${yOrders(value(m))}`;connected=true;return point;}).join(' ');
 const dots=data.map((m,i)=>value(m)==null?'':`<circle cx="${x(i)}" cy="${yOrders(value(m))}" r="5" fill="#d77b20" stroke="white" stroke-width="2"><title>${esc(m.month)}: ${format(value(m))} ${hours?'H':'ordens'}</title></circle>`).join('');
 $('calendar').innerHTML=`<div class="monthly-chart-legend"><span><i class="rate-key"></i>${indexLabel} (%)</span><span><i class="orders-key"></i>${label}</span></div><div class="monthly-chart-scroll"><svg class="monthly-chart" viewBox="0 0 ${w} ${h}" style="min-width:${w}px" role="img" aria-label="${indexLabel} e ${label} por mês"><text x="${left}" y="20" fill="#086458">${indexLabel} (%)</text><text x="${right}" y="20" text-anchor="end" fill="#a65a10">${label}</text>${grid}${bars}<path d="${points}" fill="none" stroke="#d77b20" stroke-width="3"/>${dots}</svg></div><details><summary>Ver valores do gráfico</summary><table><thead><tr><th>Mês</th><th>${indexLabel}</th><th>${label}</th></tr></thead><tbody>${data.map(m=>`<tr><td>${esc(m.month.slice(5)+'/'+m.month.slice(0,4))}</td><td>${rate(index(m))}</td><td>${format(value(m))}</td></tr>`).join('')}</tbody></table></details>`;
}
function renderAppliedFilters(f){
 const rows=[['Período',`${f.date_from?dt(f.date_from):'Sem limite inicial'} a ${f.date_to?dt(f.date_to):'Sem limite final'}`],['Agrupamento',meta.groups.find(g=>String(g.id)===String(f.group))?.name||'Todos'],['Ativos',f.assets.length?f.assets.map(a=>`${a} · ${meta.assets.find(x=>x.asset===a)?.name||a}`).join('; '):'Todos (incluindo componentes)']];
 for(const [key,label] of [['type','Tipo de ordem'],['activity_type','Tipo de atividade'],['work_center','Centro de trabalho'],['abc','Código ABC'],['condition','Condição da linha'],['text','Texto da atividade'],['search','Busca por ativo']])if(Array.isArray(f[key])?f[key].length:f[key])rows.push([label,Array.isArray(f[key])?f[key].join(', '):f[key]]);
 $('applied-filters').innerHTML=rows.map(([label,value])=>`<div><strong>${label}:</strong> ${esc(value)}</div>`).join('');
}
async function report(){$('export-plans').disabled=true;const v=++version,applied=filters();$('busy').hidden=false;let d;try{d=await api('report',applied);}finally{if(v===version)$('busy').hidden=true;}if(v!==version)return;const t=d.totals;
renderAppliedFilters(applied);
appliedPlanFilters={...applied};
detailVersion++;detailCode="";$("plan-detail").replaceChildren();
summaryData=d;selectedSummaryAsset=null;summaryVersion++;renderPlanSummary(d);
$('scope').textContent=`${num(t.plans)} planos distintos · ${num(d.undated_count)} itens sem programação datada (fora do índice). ${num(d.outside_master_orders)} ordens da IW39 não vinculadas ao mestre ficam fora desta análise.`;
const hh=v=>v===null?'—':num(v);
const cardMetrics=c=>`<strong>${rate(c.rate)}</strong><span class="card-counts"><span class="day-done">${num(c.done)} executadas</span> / <span class="day-pending">${num(c.pending)} não executadas</span> / ${num(c.planned)} previstas</span><span class="card-duration"><span class="day-done">${hh(c.duration_done)} H executada</span> / <span class="day-pending">${hh(c.duration_pending)} H não executada</span> / ${hh(c.duration_hours)} H prevista</span>`;
$('group-cards').innerHTML=`<button type="button" data-all-assets class="sap-group ${!applied.group&&!applied.assets.length&&!applied.search?'selected':''}" aria-pressed="${!applied.group&&!applied.assets.length&&!applied.search}"><b>Todos os Ativos</b>${cardMetrics(d.all_assets_totals)}</button>`+d.groups.filter(g=>g.visible!==false).map(g=>`<button type="button" data-group="${g.id}" class="sap-group ${String(g.id)===String(applied.group)?'selected':''}"><b>${esc(g.name)}</b>${cardMetrics(g)}</button>`).join('');
calendarData=d.monthly;calendar();
$('undated-note').textContent=`${num(d.undated_count)} itens sem data nos arquivos disponíveis. Não é possível atribuí-los ao período selecionado. ${d.undated_count>200?'Exibindo os primeiros 200; use filtros para restringir.':''}`;
$('undated').innerHTML='<table><thead><tr><th>Plano / item</th><th>Ativo</th><th>Atividade</th></tr></thead><tbody>'+d.undated.map(r=>`<tr><td>${esc(r.plan)} / ${esc(r.item)}</td><td>${esc(r.asset_name)}</td><td>${esc(r.description)}</td></tr>`).join('')+'</tbody></table>';
$('by-asset').innerHTML=d.by_asset.length?'<table><thead><tr><th>Ativo</th><th>Descrição</th><th>Previstas</th><th>Realizadas</th><th>Não realizadas</th><th>Índice de realização</th></tr></thead><tbody>'+d.by_asset.map(a=>`<tr data-asset="${esc(a.asset)}"><td><button type="button" class="table-link">${esc(a.asset||'Local não informado')}</button></td><td>${esc(a.name)}${a.direct_location&&a.asset?'<small>Planos cadastrados diretamente neste local</small>':''}</td><td>${num(a.planned)}</td><td class="plan-done">${num(a.done)}</td><td class="plan-pending">${num(a.pending)}</td><td><strong>${rate(a.rate)}</strong></td></tr>`).join('')+`</tbody><tfoot><tr><th colspan="2">Total · ${num(d.by_asset.length)} ativos</th><th>${num(t.planned)}</th><th>${num(t.done)}</th><th>${num(t.pending)}</th><th>${rate(t.rate)}</th></tr></tfoot></table>`:'<p>Nenhum ativo neste recorte.</p>';

enableSummarySorting('by-asset',d.by_asset,[a=>a.asset,a=>a.name,a=>a.planned,a=>a.done,a=>a.pending,a=>a.rate]);
}
async function pollImport(){polling=true;message('Importando arquivos SAP. Você pode continuar usando os filtros.');try{while(true){await new Promise(r=>setTimeout(r,2000));const m=await api('meta');if(!m.job.running){if(m.job.error)throw Error(m.job.error);await loadMeta();await report();message('Importação concluída. Dados e indicadores atualizados.');break;}}}catch(e){message(e.message,true);$('import').disabled=false;}finally{polling=false;}}
$('filters').onsubmit=run(async()=>{saveDateFilter();await report();});$('search').oninput=filterAssets;
$('clear').onclick=run(async()=>{clearFiltersKeepingDates();filterAssets();await report();});
$('group-form').onsubmit=run(async()=>{await api('groups',{name:$('group-name').value,assets:selected()});await loadMeta();await report();message('Agrupamento salvo. Selecione-o no filtro Grupo de ativos.');});
$('rules').onsubmit=run(async()=>{const codes=id=>$(id).value.trim().toUpperCase().split(/\s+/).filter(Boolean);await api('config',{done_user:codes('done-user'),not_done_user:codes('not-done-user'),plan_manter:meta.config.plan_manter,no_plan_extra:meta.config.no_plan_extra});await loadMeta();await report();message('Regras salvas. Indicadores recalculados.');});
$('import').onclick=()=>{location.assign('/configuracoes?profile='+encodeURIComponent(planProfile)+'#preventivo');};
$('source-cancel').onclick=()=>{$('source-picker').hidden=true;};
$('source-form').onsubmit=run(async()=>{
 const choices=Object.fromEntries(['IP18','IW39','IP24','IH06'].map(kind=>[kind,$('source-'+kind).value]));
 $('source-submit').disabled=true;
 try{await api('import',{choices});$('source-picker').hidden=true;$('import').disabled=true;pollImport();}
 finally{$('source-submit').disabled=false;}
});
restoreDateFilter();
$('from').onchange=saveDateFilter;$('to').onchange=saveDateFilter;
$('plan-profile').onchange=()=>{location.href='/plano-manutencao?profile='+encodeURIComponent($('plan-profile').value);};
run(async()=>{const d=await api('profiles');$('plan-profile').innerHTML=d.profiles.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');$('plan-profile').value=planProfile;await loadMeta();await report();})();

$('group-cards').onclick=run(async e=>{const button=e.target.closest('[data-group],[data-all-assets]');if(!button)return;if(button.hasAttribute('data-all-assets')){$('group').value='';$('search').value='';for(const option of $('assets').options)option.selected=false;filterAssets();}else{$('group').value=button.dataset.group;}await report();});
$('group').onchange=run(async()=>{await report();});

async function loadPlanDetail(){
 const queryVersion=++detailVersion;
 if(!appliedPlanFilters){$('plan-detail').textContent='Aguarde o carregamento dos filtros.';return;}
 const currentFilters={...appliedPlanFilters,...(selectedSummaryAsset===null?{}:{summary_asset:selectedSummaryAsset})};
 $('plan-detail').textContent='Consultando plano…';
 try{
  const d=await api('plan-detail',{...currentFilters,plan:detailCode}),t=d.totals;
  if(queryVersion!==detailVersion)return;
  const fields=[['Item','item'],['Atividade','item_text'],['Local de instalação','asset'],['Tipo de ordem','type'],['Tipo de atividade','activity_type'],['Centro de trabalho','work_center'],['Código ABC','abc'],['Condição da linha','condition'],['Ciclo','cycle'],['Unidade','unit']];
  $('plan-detail').innerHTML=`<h3>Plano ${esc(d.plan)}</h3><p>${num(d.items.length)} itens · ${num(t.planned)} ocorrências previstas · ${num(t.done)} executadas · ${num(t.pending)} não executadas · Índice: <strong>${rate(t.rate)}</strong></p><p class="muted">Mesmos filtros do painel · Período: ${currentFilters.date_from?dt(currentFilters.date_from):'sem limite inicial'} a ${currentFilters.date_to?dt(currentFilters.date_to):'sem limite final'}. Ocorrências sem data ficam fora do índice.</p>`+
  d.items.map(item=>`<details open><summary>Item ${esc(item.item)} · ${esc(item.item_text)}</summary><dl class="plan-detail-fields">${fields.map(([label,key])=>`<div><dt>${label}</dt><dd>${esc(item[key]||'—')}</dd></div>`).join('')}</dl></details>`).join('')+
  '<h3>Ordens e ocorrências do plano</h3><div class="sap-scroll"><table><thead><tr><th>Data prevista</th><th>Item / atividade</th><th>Ordem</th><th>Situação</th><th>Status SAP</th><th>Fim real</th></tr></thead><tbody>'+
  [...d.rows,...d.undated].map(r=>`<tr><td>${dt(r.planned)}<small>${r.planned?esc(r.date_source):'Sem programação datada'}</small></td><td>${esc(r.item)} · ${esc(r.description)}</td><td>${esc(r.order||'Sem ordem')}</td><td><span class="sap-badge ${r.execution==='Executado'?'done':'not-done'}">${esc(r.execution)}</span></td><td>${esc(r.user_status||'—')}<small>${esc(r.system_status||'—')}</small></td><td>${dt(r.actual_end)}</td></tr>`).join('')+'</tbody></table></div>';
 }catch(e){if(queryVersion===detailVersion)$('plan-detail').textContent=e.message;}
}

function resetInlineDetail(){
 $('plan-detail-home').append($('plan-detail'));
 document.querySelector('.inline-plan-detail')?.remove();
 document.querySelectorAll('#plan-summary tr.selected').forEach(r=>{r.classList.remove('selected');r.querySelector('button.table-link')?.setAttribute('aria-expanded','false');});
 detailVersion++;detailCode='';$('plan-detail').replaceChildren();
}
function renderPlanSummary(d){
 $('export-plans').disabled=!d.by_plan.length;
 resetInlineDetail();const t=d.totals;
 $('plan-summary').innerHTML=d.by_plan.length?'<table><thead><tr><th>Plano</th><th>Atividade(s)</th><th>Previstas</th><th>Realizadas</th><th>Não realizadas</th><th>Índice de realização</th></tr></thead><tbody>'+d.by_plan.map(p=>`<tr data-plan="${esc(p.plan)}"><td><button type="button" class="table-link">${esc(p.plan||'Sem código')}</button></td><td>${p.descriptions.map(esc).join('<br>')}</td><td>${num(p.planned)}</td><td class="plan-done">${num(p.done)}</td><td class="plan-pending">${num(p.pending)}</td><td><strong>${rate(p.rate)}</strong></td></tr>`).join('')+`</tbody><tfoot><tr><th colspan="2">Total · ${num(d.by_plan.length)} planos</th><th>${num(t.planned)}</th><th>${num(t.done)}</th><th>${num(t.pending)}</th><th>${rate(t.rate)}</th></tr></tfoot></table>`:'<p>Nenhum plano com ocorrências no recorte selecionado.</p>';
 enableSummarySorting('plan-summary',d.by_plan,[p=>p.plan,p=>p.descriptions.join(' '),p=>p.planned,p=>p.done,p=>p.pending,p=>p.rate]);
 $('plan-selection-note').textContent=selectedSummaryAsset===null?'Todos os ativos dos filtros utilizados. Clique em um plano para expandir ou recolher seus detalhes.':'Planos do ativo: '+(selectedSummaryAsset||'Local não informado');
 $('clear-summary-asset').hidden=selectedSummaryAsset===null;
}
$('by-asset').onclick=run(async e=>{
 const row=e.target.closest('tr[data-asset]');if(!row||!appliedPlanFilters)return;
 const requestVersion=++summaryVersion;selectedSummaryAsset=row.dataset.asset;
 document.querySelectorAll('#by-asset tr[data-asset]').forEach(r=>r.classList.toggle('selected',r===row));
 resetInlineDetail();$('export-plans').disabled=true;$('plan-summary').textContent='Carregando planos do ativo…';
 try{const d=await api('report',{...appliedPlanFilters,summary_asset:selectedSummaryAsset});if(requestVersion===summaryVersion)renderPlanSummary(d);}
 catch(error){if(requestVersion===summaryVersion)$('plan-summary').textContent=error.message;}
});
$('clear-summary-asset').onclick=()=>{summaryVersion++;selectedSummaryAsset=null;document.querySelectorAll('#by-asset tr.selected').forEach(r=>r.classList.remove('selected'));renderPlanSummary(summaryData);};
$('plan-summary').onclick=run(async e=>{
 const row=e.target.closest('tr[data-plan]');if(!row)return;
 if(row.classList.contains('selected')){resetInlineDetail();return;}
 resetInlineDetail();row.classList.add('selected');row.querySelector('button.table-link')?.setAttribute('aria-expanded','true');detailCode=row.dataset.plan;
 const detail=document.createElement('tr');detail.className='inline-plan-detail';const cell=document.createElement('td');cell.colSpan=6;cell.append($('plan-detail'));detail.append(cell);row.after(detail);
 await loadPlanDetail();
});

function renderGroupManager(){
 $('group-manager-list').innerHTML=meta.groups.length?meta.groups.map((g,i)=>`<div class="group-manager-row"><b>${esc(g.name)}</b><span>${num(g.assets.length)} locais</span><label class="group-visible"><input type="checkbox" data-group-visible="${g.id}" ${g.visible?'checked':''}> Exibir agrupamento</label><div><button type="button" data-group-action="up" data-id="${g.id}" ${i===0?'disabled':''} aria-label="Subir ${esc(g.name)}">↑ Subir</button> <button type="button" data-group-action="down" data-id="${g.id}" ${i===meta.groups.length-1?'disabled':''} aria-label="Descer ${esc(g.name)}">↓ Descer</button> <button type="button" data-group-action="edit" data-id="${g.id}">Editar</button> <button type="button" data-group-action="delete" data-id="${g.id}">Excluir</button></div></div>`).join(''):'<p>Nenhum agrupamento salvo.</p>';
}
const handleGroupAction=run(async e=>{
 const button=e.target.closest('[data-group-action]');if(!button)return;
 const id=Number(button.dataset.id),g=meta.groups.find(g=>g.id===id);if(!g)return;
 const action=button.dataset.groupAction;
 if(action==='edit'){
  $('group-edit-id').value=id;$('group-edit-name').value=g.name;
  const assets=new Map(meta.assets.map(a=>[a.asset,a.name]));for(const a of g.assets)if(!assets.has(a))assets.set(a,a);
  $('group-edit-assets').innerHTML=[...assets].map(([a,name])=>`<option value="${esc(a)}" ${g.assets.includes(a)?'selected':''}>${esc(a)} · ${esc(name)}</option>`).join('');
  $('group-edit-form').hidden=false;$('group-edit-name').focus();return;
 }
 button.disabled=true;
 try{
  if(action==='delete'){
   if(!confirm(`Excluir o agrupamento “${g.name}”? Os ativos e planos permanecerão no cadastro.`))return;
   await api('groups/delete',{id});
   if($('group').value===String(id))$('group').value='';
   if($('group-edit-id').value===String(id))$('group-edit-form').hidden=true;
  }else{
   const ids=meta.groups.map(g=>g.id),i=ids.indexOf(id),j=i+(action==='up'?-1:1);if(j<0||j>=ids.length)return;
   [ids[i],ids[j]]=[ids[j],ids[i]];await api('groups/reorder',{ids});
  }
  await loadMeta();await report();
 }finally{button.disabled=false;}
});
$('group-manager-list').onclick=e=>{if(e.target.closest('[data-group-action]'))return handleGroupAction(e);};
$('group-edit-cancel').onclick=()=>{$('group-edit-form').hidden=true;};
$('group-edit-form').onsubmit=run(async()=>{
 await api('groups',{id:Number($('group-edit-id').value),name:$('group-edit-name').value,assets:[...$('group-edit-assets').selectedOptions].map(o=>o.value)});
 $('group-edit-form').hidden=true;await loadMeta();await report();message('Agrupamento atualizado.');
});

$('chart-secondary').onchange=calendar;

$('export-plans').onclick=run(async()=>{
 const button=$('export-plans');button.disabled=true;button.textContent='Exportando…';
 const selectionVersion=summaryVersion;
 const exportFilters={...appliedPlanFilters,...(selectedSummaryAsset===null?{}:{summary_asset:selectedSummaryAsset})};
 const planOrder=[...document.querySelectorAll('#plan-summary tr[data-plan]')].map(row=>row.dataset.plan);
 try{
  const response=await fetch('/api/sap/export-plans?profile='+encodeURIComponent(planProfile),{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content},body:JSON.stringify({filters:exportFilters,plan_order:planOrder})});
  if(!response.ok){const error=await response.json();throw Error(error.error||'Não foi possível exportar.');}
  const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='realizacao_por_plano.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
  message('Excel gerado com os planos listados e suas ordens e ocorrências.');
 }finally{button.textContent='Exportar Excel';if(selectionVersion===summaryVersion)button.disabled=false;}
});

$('group-manager-list').onchange=run(async e=>{
 const checkbox=e.target.closest('[data-group-visible]');if(!checkbox)return;
 checkbox.disabled=true;
 try{await api('groups/visibility',{id:Number(checkbox.dataset.groupVisible),visible:checkbox.checked});await loadMeta();await report();}
 catch(error){checkbox.checked=!checkbox.checked;throw error;}
 finally{checkbox.disabled=false;}
});
