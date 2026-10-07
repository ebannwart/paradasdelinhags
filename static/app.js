'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (n, digits=0) => Number(n || 0).toLocaleString('pt-BR',{maximumFractionDigits:digits});
const dateText = (s, time=false) => s ? new Date(s).toLocaleString('pt-BR',time ? {dateStyle:'short',timeStyle:'short'} : {dateStyle:'short'}) : '—';
const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
const palette = ['#147d75','#4d83ab','#e0a354','#8074b3','#58a497','#cf7972','#7494a5','#b39160','#98b35e'];
const multiKeys = ['year','month','equipment','offender','modality','responsible','files'];
const textKeys = ['text','date_from','date_to','min_minutes','max_minutes'];
let meta = {}, filters = {}, currentView = 'dashboard', page = 1, recordData = {rows:[],total:0,pages:1};
let selected = new Set(), allFiltered = false, summaryData = null, pending = 0, requestVersion = 0;
let toastTimer, pollTimer, importing = false, createFromRecords = false;

function toast(message, error=false) {
  $('toast').textContent = message; $('toast').className = error ? 'error' : ''; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true,error ? 9000 : 5000);
}
async function api(path, body, raw=false) {
  pending++; $('loading').hidden = false;
  try {
    const options = body === undefined ? {} : {method:'POST',headers:{'X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content},body:body instanceof FormData ? body : JSON.stringify(body)};
    if (body !== undefined && !(body instanceof FormData)) options.headers['Content-Type'] = 'application/json';
    const response = await fetch(path,options);
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error || 'Falha ao comunicar com a aplicação.'); }
    return raw ? response : response.json();
  } finally { pending--; $('loading').hidden = pending === 0; }
}
function run(fn) { return async (...args) => { try { await fn(...args); } catch(error) { console.error(error); toast(error.message,true); } }; }
function options(id, rows, placeholder=null) {
  const element = $(id), previous = [...element.selectedOptions].map(x=>x.value);
  element.innerHTML = (placeholder !== null ? `<option value="">${esc(placeholder)}</option>` : '') + rows.map(r => `<option value="${esc(r.value)}">${esc(r.label)}</option>`).join('');
  [...element.options].forEach(o => o.selected = previous.includes(o.value));
  if (!element.multiple && element.selectedIndex < 0) element.selectedIndex = 0;
}
const simpleOptions = rows => rows.map(v => ({value:v,label:v}));
function readFilters() {
  const out = {};
  multiKeys.forEach(k => { const vals = [...$('f-'+k).selectedOptions].map(o=>o.value); if(vals.length) out[k]=vals; });
  textKeys.forEach(k => { if($('f-'+k).value.trim()) out[k]=$('f-'+k).value.trim(); });
  if($('f-overlap').checked) out.overlap = true;
  return out;
}
function writeFilters() {
  multiKeys.forEach(k => [...$('f-'+k).options].forEach(o => o.selected = (filters[k] || []).map(String).includes(o.value)));
  textKeys.forEach(k => $('f-'+k).value = filters[k] || '');
  $('f-overlap').checked = !!filters.overlap;
  const labels = {year:'Ano',month:'Mês',equipment:'Equipamento',offender:'Ofensor',modality:'Modalidade',responsible:'Responsável',files:'Arquivo',type:'Tipo',day:'Dia',text:'Busca',date_from:'Desde',date_to:'Até',min_minutes:'Mín. min',max_minutes:'Máx. min',overlap:'Sobreposições'};
  $('active-filters').innerHTML = Object.entries(filters).filter(([k])=>labels[k]).map(([k,v]) => {
    let text = Array.isArray(v) ? v.map(x => {const option = [...$('f-'+k).options].find(o=>o.value===String(x)); return option ? option.text : x;}).join(', ') : String(v);
    if(k==='overlap') text='sim';
    return `<span class="chip">${esc(labels[k])}: ${esc(text)}</span>`;
  }).join('');
}
async function loadMeta() {
  meta = await api('/api/meta');
  ['year','equipment','responsible'].forEach(k => options('f-'+k,simpleOptions(meta[k])));
  options('f-month',months.map((v,i)=>({value:String(i+1),label:v})));
  options('f-modality',meta.modalities.map(m=>({value:m,label:m+' · '+meta.modality_labels[m]})));
  options('maintenance-equipment',simpleOptions(meta.equipment));
  options('maintenance-files',meta.files.map(f=>({value:String(f.id),label:f.name})));
  options('f-files',meta.files.map(f=>({value:String(f.id),label:f.name})));
  options('f-offender',[{value:'none',label:'Não classificado'},...meta.offenders.map(o=>({value:String(o.id),label:o.name}))]);
  options('bulk-offender',meta.offenders.map(o=>({value:o.id,label:o.name})),'Remover ofensor (não classificado)');
  options('offender-equipment',simpleOptions(meta.equipment));
  $('tolerance').value = meta.tolerance;
  renderOffenders(); renderFiles(); writeFilters();
}
const viewInfo = {dashboard:['Visão geral','Entenda as paradas. Encontre as recorrências.'],maintenance:['KPI manutenção','Disponibilidade, confiabilidade e reparo. Metas por linha.'],records:['Lançamentos','Explore as descrições e classifique os problemas recorrentes.'],offenders:['Ofensores','Organize os problemas que merecem acompanhamento.'],files:['Arquivos e ajustes','Gerencie suas fontes e as regras de agrupamento.']};
async function showView(name, refresh=true) {
  currentView=name;
  const path=name==='maintenance'?'/kpi-manutencao':'/';
  if(location.pathname!==path)history.pushState({view:name},'',path);
  document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!=='view-'+name);
  document.querySelectorAll('.nav').forEach(v=>v.classList.toggle('active',v.dataset.view===name));
  $('page-title').textContent=viewInfo[name][0]; $('page-description').textContent=viewInfo[name][1];
  $('filters-panel').hidden = !['dashboard','records'].includes(name);
  $('export').hidden = !['dashboard','records'].includes(name);
  if(refresh) await refreshView();
}
async function refreshView() {
  if(currentView==='dashboard') await loadSummary();
  if(currentView==='records') await loadRecords();
  if(currentView==='offenders') renderOffenders();
  if(currentView==='files') renderFiles();
  if(currentView==='maintenance') await loadMaintenance();
}
async function loadSummary() {
  const version=++requestVersion;
  const data=await api('/api/summary',{...filters,stack:$('stack').value});
  if(version!==requestVersion) return;
  summaryData=data; const t=data.totals;
  $('kpi-minutes').textContent=fmt(t.minutes,1);
  $('kpi-hours').textContent=`minutos · ${fmt(t.minutes/60,1)} horas`;
  $('kpi-events').textContent=fmt(t.events); $('kpi-records').textContent=fmt(t.records);
  $('kpi-unclassified').textContent=t.minutes ? fmt(100*t.unclassified_minutes/t.minutes,1)+'%' : '—';
  $('date-range').textContent=t.records ? `${dateText(t.first_date)} — ${dateText(t.last_date)}` : 'Nenhum lançamento neste recorte';
  let notice = `Agrupamento: mesmo equipamento, intervalo de até ${fmt(meta.tolerance,1)} min. Datas usam o início do lançamento. Meses sem registros nas fontes selecionadas aparecem como lacunas; a presença de dados não garante um mês completo.`;
  if(t.overlaps) notice += ` Atenção: ${fmt(t.overlaps)} lançamentos filtrados têm sobreposição de horário. A soma dos minutos pode incluir tempos sobrepostos.`;
  if(!meta.files.length) notice='Comece em “Arquivos e ajustes”: selecione e importe as planilhas que deseja analisar.';
  $('analysis-notice').textContent=notice; $('analysis-notice').className='notice'+(t.overlaps ? ' warning':'');
  renderCharts();
}
function plot(id,traces,layout={},onClick=null) {
  const base={paper_bgcolor:'transparent',plot_bgcolor:'transparent',separators:',.',font:{family:'Segoe UI, Arial',size:11,color:'#68808d'},margin:{l:60,r:25,t:22,b:55},colorway:palette,hovermode:'closest',bargap:.28,
    xaxis:{showgrid:false,automargin:true,tickfont:{size:10}},yaxis:{gridcolor:'#eaf0f3',zeroline:false,rangemode:'tozero',automargin:true},legend:{orientation:'h',y:-.24,x:0,font:{size:10}},...layout};
  if(!traces.some(t=>t.y?.some(v=>v!==null&&v!==undefined)||t.x?.length&&t.orientation==='h')) base.annotations=[{text:layout.emptyMessage||'Sem dados para este recorte',xref:'paper',yref:'paper',x:.5,y:.5,showarrow:false,font:{size:12,color:'#8a9ca6'}}];
  delete base.emptyMessage;
  Plotly.react(id,traces,base,{responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d'],toImageButtonOptions:{format:'png',filename:id,width:1400,height:600}}).then(()=>{
    const target=$(id); target.removeAllListeners('plotly_click'); if(onClick) target.on('plotly_click',run(e=>onClick(e.points[0])));
  });
}
async function drill(extra) {filters={...filters,...extra};writeFilters();page=1;clearSelection();await showView('records');}
function renderCharts() {
  if(!summaryData || currentView!=='dashboard')return;
  const d=summaryData, metric=$('metric').value, label={minutes:'Minutos',events:'Eventos',records:'Lançamentos'}[metric];
  const lookup=Object.fromEntries(d.months.map(m=>[m.period,m])), covered=new Set(d.coverage.map(c=>c.period));
  const y=d.periods.map(p=>lookup[p]?.[metric] ?? (covered.has(p)?0:null));
  const periodLabels=d.periods.map(p=>months[Number(p.slice(5))-1]+'/'+p.slice(0,4));
  const periodAxis={type:'category',tickmode:'array',tickvals:periodLabels.filter((_,i)=>i%Math.max(1,Math.ceil(periodLabels.length/12))===0),tickangle:-45,automargin:true,tickfont:{size:10}};
  plot('chart-timeline',[{x:periodLabels,y,type:'bar',marker:{color:'#147d75'},customdata:d.periods,hovertemplate:'%{x}<br>%{y:,.1f} '+label+'<extra></extra>'}],{yaxis:{title:{text:label},gridcolor:'#eaf0f3',rangemode:'tozero'},xaxis:periodAxis},p=>drill({year:[p.customdata.slice(0,4)],month:[String(Number(p.customdata.slice(5)))]}));
  const stackGroups=new Map(d.stacks.map(s=>[s.key,s.name]));
  const stackLookup=new Map(d.stacks.map(s=>[s.key+'|'+s.period,s.minutes]));
  plot('chart-stack',[...stackGroups].map(([key,name],i)=>({name,type:'bar',x:periodLabels,y:d.periods.map(p=>stackLookup.get(key+'|'+p)??(covered.has(p)?0:null)),customdata:d.periods.map(p=>[p,key]),marker:{color:d.stack==='offender' ? meta.offenders.find(o=>String(o.id)===String(key))?.color||palette[i%palette.length] : palette[i%palette.length]},hovertemplate:'%{x}<br>%{y:,.1f} min<extra>'+esc(name)+'</extra>'})),{barmode:'stack',xaxis:periodAxis,yaxis:{title:{text:'Minutos'},gridcolor:'#eaf0f3',rangemode:'tozero'}},p=>drill({year:[p.customdata[0].slice(0,4)],month:[String(Number(p.customdata[0].slice(5)))],[d.stack]:[String(p.customdata[1])]}));
  renderOffenderCharts(d,covered);
  const equipments=[...d.groups.equipment].sort((a,b)=>b[metric]-a[metric]);
  plot('chart-equipment',[{type:'bar',x:equipments.map(r=>r.name),y:equipments.map(r=>r[metric]),customdata:equipments.map(r=>r.key),marker:{color:'#4d83ab'},hovertemplate:'%{x}<br>%{y:,.1f} '+label+'<extra></extra>'}],{yaxis:{title:{text:label},gridcolor:'#eaf0f3',rangemode:'tozero'}},p=>drill({equipment:[p.customdata]}));
}
function renderOffenderCharts(d,covered) {
  const metric=$('pareto-metric').value,label=metric==='minutes'?'Minutos':'Paradas (eventos)',digits=metric==='minutes'?1:0;
  const ranked=[...d.groups.offender].sort((a,b)=>b[metric]-a[metric]||a.name.localeCompare(b.name,'pt-BR')).slice(0,15);
  const total=d.groups.offender.reduce((sum,r)=>sum+r[metric],0);let cumulative=0;
  $('pareto-note').textContent=metric==='events'?'Quantidade = eventos distintos por ofensor, conforme o agrupamento configurado. Um evento com diferentes ofensores conta em cada categoria; o percentual acumulado usa a soma dessas contagens.':'Tempo registrado em minutos. O percentual acumulado usa todos os ofensores do recorte, incluindo os que não aparecem entre os 15 maiores.';
  const traces=[{type:'bar',x:ranked.map(r=>r.name),y:ranked.map(r=>r[metric]),customdata:ranked.map(r=>r.key),name:label,
    text:$('pareto-labels').checked?ranked.map(r=>fmt(r[metric],digits)):[],textposition:$('pareto-labels').checked?'outside':'none',cliponaxis:false,
    marker:{color:ranked.map(r=>r.key==='none'?'#a9b6bd':meta.offenders.find(o=>String(o.id)===String(r.key))?.color||'#147d75')},hovertemplate:'%{x}<br>%{y:,.'+digits+'f} '+label+'<extra></extra>'},
    {type:'scatter',mode:'lines+markers',x:ranked.map(r=>r.name),y:ranked.map(r=>{cumulative+=r[metric];return total?100*cumulative/total:0;}),customdata:ranked.map(r=>r.key),name:'% acumulado',yaxis:'y2',line:{color:'#d69a46',width:3},hovertemplate:'%{y:.1f}% acumulado<extra></extra>'}];
  plot('chart-offenders',traces,{margin:{l:65,r:55,t:40,b:120},showlegend:false,xaxis:{tickangle:-30,automargin:true},yaxis:{title:{text:label},gridcolor:'#eaf0f3',range:[0,Math.max(1,...ranked.map(r=>r[metric]))*1.2]},yaxis2:{overlaying:'y',side:'right',range:[0,110],ticksuffix:'%',showgrid:false}},p=>drill({offender:[String(p.customdata)]}));
  const heatMetric=$('heatmap-metric').value,heatLabel=heatMetric==='minutes'?'Minutos':'Paradas',heatDigits=heatMetric==='minutes'?1:0;
  const annual=$('heatmap-group').value==='year';
  const heatCovered=new Set([...covered].map(p=>annual?p.slice(0,4):p));
  const last=[...heatCovered].sort().at(-1);
  const periods=[...new Set(d.periods.map(p=>annual?p.slice(0,4):p))].filter(p=>last&&p<=last);
  const values=new Map((annual?d.offender_years:d.offender_months).map(r=>[r.key+'|'+r.period,r[heatMetric]]));
  const rows=[...d.groups.offender].sort((a,b)=>(values.get(b.key+'|'+last)??0)-(values.get(a.key+'|'+last)??0)||b[heatMetric]-a[heatMetric]||a.name.localeCompare(b.name,'pt-BR'));
  $('heatmap-note').textContent=`Equipamento selecionado - ${filters.equipment?.length?filters.equipment.join(', '):'Todos os equipamentos'}`;
  const chart=$('chart-heatmap');chart.style.height=Math.max(300,rows.length*32+130)+'px';chart.style.minWidth=Math.max(0,periods.length*65+210)+'px';
  const z=rows.map(r=>periods.map(p=>values.get(r.key+'|'+p)??(heatCovered.has(p)?0:null)));
  plot('chart-heatmap',rows.length&&periods.length?[{type:'heatmap',x:periods.map(p=>annual?p:months[Number(p.slice(5))-1]+'/'+p.slice(0,4)),y:rows.map(r=>r.name),z,
    customdata:rows.map(r=>periods.map(p=>[r.key,p])),colorscale:[[0,'#f0f6f5'],[0.3,'#a5d5c9'],[0.65,'#389b8b'],[1,'#105b54']],zmin:0,
    texttemplate:'%{z:,.'+heatDigits+'f}',textfont:{size:10},hoverongaps:false,xgap:2,ygap:2,
    colorbar:{title:{text:heatLabel},thickness:12},hovertemplate:'%{y}<br>%{x}<br>%{z:,.'+heatDigits+'f} '+heatLabel+'<extra></extra>'}]:[],
    {margin:{l:155,r:80,t:15,b:80},xaxis:{type:'category',tickangle:-45,automargin:true},yaxis:{type:'category',autorange:'reversed',automargin:true}},p=>{if(p.z!==null&&p.customdata)drill({offender:[String(p.customdata[0])],year:[p.customdata[1].slice(0,4)],...(annual?{}:{month:[String(Number(p.customdata[1].slice(5)))]})});});
}
function clearSelection() {selected.clear();allFiltered=false;updateSelection();}
function updateSelection() {
  const count=allFiltered?recordData.total:selected.size;
  $('selection-count').textContent=count ? `${fmt(count)} selecionado(s)${allFiltered?' · todos os resultados filtrados':''}` : 'Nenhum selecionado';
  $('assign-offender').disabled=!count; $('assign-type').disabled=!count;
  $('select-all-results').disabled=!recordData.total;
  $('select-page').checked=recordData.rows.length>0&&recordData.rows.every(r=>allFiltered||selected.has(r.id));
  document.querySelectorAll('.record-check').forEach(e=>e.checked=allFiltered||selected.has(e.dataset.id));
}
function offenderOptions(current=null) {
  return `<option value=""${current===null?' selected':''}>Não classificado</option>`+meta.offenders.map(o=>`<option value="${o.id}"${o.id===current?' selected':''}>${esc(o.name)}</option>`).join('');
}
async function loadRecords() {
  const version=++requestVersion;
  const data=await api('/api/records',{filters,page});
  if(version!==requestVersion)return;
  recordData=data;page=data.page;
  $('records-count').textContent=`${fmt(data.total)} lançamentos encontrados · 50 por página`;
  $('records-body').innerHTML=data.rows.length?data.rows.map(r=>`<tr><td><input class="record-check" type="checkbox" data-id="${r.id}" aria-label="Selecionar ${esc(r.equipment)} em ${esc(dateText(r.start,true))}"></td><td class="equipment"><strong>${esc(r.equipment)}</strong><small>${dateText(r.start,true)}</small><small>Até ${dateText(r.end,true)}</small>${r.overlap?'<span class="overlap-label">Sobreposição</span>':''}</td><td class="minutes">${fmt(r.minutes,1)}<small>min</small></td><td><span class="modality-label">${esc(r.modality)}</span><small>${esc(r.reason)}</small>${r.stop_type!=='Demais paradas'?`<span class="type-label">${esc(r.stop_type)}</span>`:''}</td><td class="observation"><div>${esc(r.observation||'Sem observação')}</div></td><td><select class="row-offender" data-id="${r.id}" aria-label="Ofensor do lançamento ${esc(r.equipment)} ${esc(dateText(r.start,true))}">${offenderOptions(r.offender_id)}</select></td><td><button class="text-button detail-button" data-id="${r.id}">Detalhes ↗</button></td></tr>`).join(''):'<tr><td colspan="7" class="empty">Nenhum lançamento encontrado. Ajuste os filtros ou importe arquivos.</td></tr>';
  $('page-info').textContent=`Página ${data.page} de ${fmt(data.pages)}`;
  $('previous-page').disabled=data.page<=1;$('next-page').disabled=data.page>=data.pages;
  updateSelection();
}
async function bulkClassify(field) {
  const value=field==='offender_id'?$('bulk-offender').value:$('bulk-type').value;
  const result=await api('/api/classify',{field,value:value||null,ids:[...selected],all_filtered:allFiltered,filters,expected_count:allFiltered?recordData.total:selected.size});
  toast(`${fmt(result.updated)} lançamento(s) atualizado(s).`);clearSelection();await loadRecords();
}
function openOffender(id=null) {
  const row=meta.offenders.find(o=>o.id===id);
  $('offender-dialog-title').textContent=row?'Editar ofensor':'Novo ofensor';
  $('offender-id').value=row?.id||'';$('offender-name').value=row?.name||'';
  $('offender-description').value=row?.description||'';$('offender-color').value=row?.color||'#147d75';
  [...$('offender-equipment').options].forEach(o=>o.selected=(row?.equipment||[]).includes(o.value));
  $('offender-dialog').showModal();$('offender-name').focus();
}
function renderOffenders() {
  $('offenders-list').innerHTML=meta.offenders.length?meta.offenders.map(o=>`<article class="panel offender-card" style="border-top-color:${o.color}"><h3>${esc(o.name)}</h3><p>${esc(o.description||'Sem descrição adicional.')}</p><p>${o.equipment.length?esc(o.equipment.join(', ')):'Todos os equipamentos'}</p><div class="actions"><button class="text-button offender-view" data-id="${o.id}">Analisar ofensor ↗</button><button class="button secondary offender-edit" data-id="${o.id}">Editar</button></div></article>`).join(''):'<div class="panel empty">Seu catálogo ainda está vazio. Crie o primeiro ofensor e classifique os lançamentos pela descrição.</div>';
}
function renderFiles() {
  const checked=[...document.querySelectorAll('.local-file:checked')].map(e=>e.value);
  $('local-files').innerHTML=(meta.local_files||[]).map(name=>`<label><input class="local-file" type="checkbox" value="${esc(name)}"${checked.includes(name)?' checked':''}>${esc(name)}</label>`).join('')||'<p class="muted">Nenhum .xlsx na pasta do projeto.</p>';
  $('files-body').innerHTML=meta.files.length?meta.files.map(f=>`<tr><td><strong>${esc(f.name)}</strong><small>Importado: ${dateText(f.imported_at,true)}</small></td><td>${dateText(f.min_date)} — ${dateText(f.max_date)}</td><td>${fmt(f.row_count)}</td><td>${fmt(f.duplicate_count)}</td><td>${fmt(f.invalid_count)}</td><td><button class="text-button file-issues" data-id="${f.id}">Validação</button></td></tr>`).join(''):'<tr><td colspan="6" class="empty">Nenhum arquivo importado.</td></tr>';
}
function setImportBusy(busy) {importing=busy;$('import-local').disabled=busy;$('import-upload').disabled=busy;$('settings-form').querySelector('button').disabled=busy;}
async function pollImport() {
  const state=await api('/api/import/status');setImportBusy(state.running);
  if(state.total) {
    $('import-progress').hidden=false;
    $('import-progress').innerHTML=`<strong>${state.running?'Importando '+esc(state.current):'Importação concluída'}</strong><p class="muted">${state.completed} de ${state.total} arquivos processados</p><div class="progress-track"><div class="progress-fill" style="width:${100*state.completed/state.total}%"></div></div>${state.results.map(r=>`<div class="import-result ${r.status==='error'?'error':''}"><strong>${esc(r.name)}</strong> · ${r.status==='error'?esc(r.error):r.status==='unchanged'?'já atualizado':`${fmt(r.rows)} linhas válidas · ${fmt(r.duplicates)} duplicadas · ${fmt(r.invalid)} inválidas`}</div>`).join('')}`;
  }
  if(state.running) {clearTimeout(pollTimer);pollTimer=setTimeout(run(pollImport),1500);}
  else if(state.total) {await loadMeta();await refreshView();}
}
async function showDetail(id) {
  const d=await api('/api/records/'+id),r=d.record;
  const eventMinutes=d.event_rows.reduce((s,row)=>s+row.minutes,0);
  const first=d.event_rows[0]?.start,last=d.event_rows.reduce((m,row)=>row.end>m?row.end:m,'');
  const elapsed=first&&last?(new Date(last)-new Date(first))/60000:0;
  $('detail-content').innerHTML=`<div class="detail-grid"><div><span>Equipamento</span><strong>${esc(r.equipment)}</strong></div><div><span>Início</span>${dateText(r.start,true)}</div><div><span>Fim</span>${dateText(r.end,true)}</div><div><span>Tempo registrado</span>${fmt(r.minutes,2)} min</div><div><span>Modalidade</span>${esc(r.modality)}</div><div><span>Responsável original</span>${esc(r.responsible_original)}</div><div><span>Ofensor</span>${esc(r.offender_name||'Não classificado')}</div><div><span>Tipo de parada</span>${esc(r.stop_type)}${r.type_override?' (manual)':' (automático)'}</div><div><span>Equipe / turno</span>${esc(r.team)} / ${esc(r.shift)}</div></div><h3>Motivo</h3><p>${esc(r.reason)}</p><h3>Observação</h3><div class="detail-text">${esc(r.observation||'Sem observação')}</div><div class="source-note">Origem: ${d.sources.map(s=>`${esc(s.name)} · ${esc(s.sheet)} · linha ${s.row_number}`).join('<br>')}</div><h3>Evento completo · ${d.event_rows.length} lançamento(s)</h3><p class="muted">${fmt(eventMinutes,1)} min registrados · ${fmt(elapsed,1)} min entre o primeiro início e o último fim. Inclui lançamentos fora do filtro atual.</p><div class="table-wrap"><table><thead><tr><th>Início / fim</th><th>Min</th><th>Modalidade / motivo</th><th>Ofensor</th></tr></thead><tbody>${d.event_rows.map(e=>`<tr><td>${dateText(e.start,true)}<small>${dateText(e.end,true)}</small></td><td>${fmt(e.minutes,1)}</td><td>${esc(e.modality)}<small>${esc(e.reason)}</small></td><td>${esc(e.offender_name||'Não classificado')}</td></tr>`).join('')}</tbody></table></div>`;
  $('detail-dialog').showModal();
}
const maintenanceSpecs = {
  imc:{title:'IMC',unit:'%',formula:'IMC = [(ME + MM) / tempo calendário] × 100',direction:'max',color:'#147d75'},
  dgfm:{title:'DGFM',unit:'%',formula:'DGFM = [1 − (ME + MM + Preventiva) / tempo calendário] × 100',direction:'min',color:'#4d83ab'},
  mtbf:{title:'MTBF',unit:'h',formula:'MTBF = [tempo calendário − (ME + MM)] / eventos com ME ou MM / 60',direction:'min',color:'#8074b3'},
  mttr:{title:'MTTR',unit:'min',formula:'MTTR = (ME + MM) / eventos com ME ou MM',direction:'max',color:'#bd853d'},
  failure_events:{title:'Eventos de falha',unit:'eventos/mês',formula:'Anual = eventos distintos do ano / meses com dados · Mensal = eventos distintos do mês',direction:'max',color:'#527eab'}
};
let maintenanceData = null, maintenanceVersion=0;
async function loadMaintenance() {
  const equipment=$('maintenance-equipment').value;
  const version=++maintenanceVersion;
  $('targets-fields').disabled=true;
  if(!equipment){$('maintenance-context').textContent='Importe as planilhas em Arquivos e ajustes para calcular os indicadores.';return;}
  const data=await api('/api/maintenance',{equipment,files:[...$('maintenance-files').selectedOptions].map(o=>o.value)});
  if(version!==maintenanceVersion)return;
  maintenanceData=data;
  $('target-equipment').textContent=equipment;
  Object.keys(maintenanceSpecs).forEach(key=>$('target-'+key).value=data.targets[key]??'');
  $('targets-fields').disabled=false;
  const latest=data.annual.find(y=>y.period===String(data.latest_year));
  const overlaps=data.annual.reduce((sum,y)=>sum+y.overlaps,0);
  let notice=`Linha ${equipment} · Base calendário 24×7 · Mensal: ${data.latest_year??'sem dados'} · ${data.files.map(f=>f.name).join(', ')}. `;
  if(latest)notice+=`${data.latest_year}: ${latest.months_with_data} mês(es) com dados da linha; ${fmt(latest.calendar_hours,1)} horas calendário consideradas${latest.partial?' (ano parcial)':''}. `;
  if(overlaps)notice+=`${fmt(overlaps)} ocorrências de lançamentos sobrepostos no histórico anual; a soma dos minutos pode incluir sobreposições. `;
  if(data.outside_minutes>.001)notice+=`${fmt(data.outside_minutes,2)} min ficam fora da cobertura das fontes e não entram nos indicadores. `;
  notice+='N = 0 deixa MTBF e MTTR sem valor. Meses sem dados não são tratados como 100% disponíveis.';
  $('maintenance-context').textContent=notice;
  $('maintenance-context').className='notice'+(overlaps?' warning':'');
  $('modality-legend').innerHTML=meta.modalities.map(m=>`<span class="chip"><strong>${esc(m)}</strong> · ${esc(meta.modality_labels[m])}</span>`).join('')+'<p class="field-help">Preventiva tem prioridade sobre o responsável original. O ajuste manual do tipo de parada prevalece. As outras modalidades são mutuamente exclusivas; PP exclui Preventiva e EX recebe todas as demais paradas.</p>';
  renderMaintenance();
}
function maintenanceValue(value,unit) {return value===null||value===undefined?'—':fmt(value,2)+' '+unit;}
function renderMaintenance() {
  if(!maintenanceData||currentView!=='maintenance')return;
  const data=maintenanceData;
  $('maintenance-charts').innerHTML=Object.entries(maintenanceSpecs).map(([key,spec])=>{
    const target=data.targets[key],targetText=target===null?'Sem meta cadastrada':`Meta ${spec.direction==='min'?'≥':'≤'} ${maintenanceValue(target,spec.unit)}`;
    return `<section class="maintenance-indicator"><div class="section-line"><div><h2>${spec.title}${key==='failure_events'?'':key==='imc'?' · Paradas corretivas':spec.unit==='%'?' · Disponibilidade':spec.unit==='min'?' · Minutos por falha':' · Horas por falha'}</h2><p class="formula">${esc(spec.formula)}</p></div></div><div class="maintenance-pair"><article class="panel chart-card"><div class="section-line"><div><h2>Histórico anual</h2><p>${key==='failure_events'?'Média mensal · eventos do ano ÷ meses com dados':'Índice calculado pelos totais de cada ano'}</p></div><span class="badge chart-target">${esc(targetText)}${target===null?'':' · '+new Date().getFullYear()}</span></div><div class="chart" id="maintenance-${key}-annual"></div></article><article class="panel chart-card"><div class="section-line"><div><h2>Mensal · ${data.latest_year??'—'}</h2><p>${key==='failure_events'?'Quantidade de eventos em cada mês':'Ano mais recente das fontes selecionadas'}</p></div><span class="badge chart-target">${esc(targetText)}</span></div><div class="chart" id="maintenance-${key}-monthly"></div></article></div></section>`;
  }).join('');
  for(const [key,spec] of Object.entries(maintenanceSpecs)) {
    for(const scope of ['annual','monthly']) {
      const rows=scope==='annual'?data.annual:data.monthly;
      const currentYear=String(new Date().getFullYear());
      const targetIndex=scope==='annual'?rows.findIndex(r=>r.period===currentYear):-1;
      const target=scope==='annual'&&targetIndex<0?null:data.targets[key];
      const labels=rows.map(r=>(scope==='annual'?r.period:months[r.month-1])+(r.partial?'*':''));
      const colors=rows.map(r=>r[key]===null||target===null||(scope==='annual'&&r.period!==currentYear)?spec.color:(spec.direction==='min'?r[key]>=target:r[key]<=target)?'#147d75':'#c57663');
      const details=rows.map(r=>[
        r.period,fmt(r.calendar_hours,2),fmt(r.corrective_minutes,2),fmt(r.preventive_minutes,2),fmt(r.failures),
        r.partial?'Período parcial':'',r.errors.join(' '),r.months_with_data??1
      ]);
      const yaxis={title:{text:key==='failure_events'?'Eventos/mês':key==='imc'?'Paradas corretivas (%)':spec.unit==='%'?'Disponibilidade (%)':spec.unit==='min'?'Minutos':'Horas'},gridcolor:'#eaf0f3',rangemode:'tozero',automargin:true};
      if(key==='imc')yaxis.range=[0,Math.max(target??0,...rows.map(r=>r[key]??0),1)*1.22];
      else if(spec.unit==='%')yaxis.range=[0,110];
      else if(target!==null)yaxis.range=[0,Math.max(target,...rows.map(r=>r[key]??0),1)*1.22];
      const layout={margin:{l:52,r:18,t:35,b:45},yaxis,xaxis:{type:'category',tickfont:{size:10},automargin:true},showlegend:false};
      if(rows.some(r=>r.records))layout.emptyMessage=rows.every(r=>!r.failures)&&spec.unit!=='%'?'Sem eventos de falha (N = 0)':'Índice indisponível; consulte a memória de cálculo';
      layout.shapes=target===null?[]:[{type:'line',xref:scope==='annual'?'x':'paper',
        x0:scope==='annual'?targetIndex-.36:0,x1:scope==='annual'?targetIndex+.36:1,
        yref:'y',y0:target,y1:target,line:{color:'#ad632e',dash:'dot',width:2}}];
      plot(`maintenance-${key}-${scope}`,[{type:'bar',x:labels,y:rows.map(r=>r[key]),name:spec.title,marker:{color:colors},customdata:details,text:rows.map(r=>r[key]===null?'':fmt(r[key],key==='failure_events'&&scope==='monthly'?0:2)),textposition:'outside',cliponaxis:false,textfont:{size:10},hovertemplate:key==='failure_events'?'%{customdata[0]}<br>'+ (scope==='annual'?'Eventos no ano: %{customdata[4]}<br>Meses com dados: %{customdata[7]}<br>Média: %{y:.2f} eventos/mês':'Eventos no mês: %{y:.0f}')+'<br>%{customdata[5]}<extra></extra>':'%{customdata[0]}<br>'+spec.title+': %{y:.2f} '+spec.unit+'<br>Calendário: %{customdata[1]} h<br>ME + MM: %{customdata[2]} min<br>Preventiva: %{customdata[3]} min<br>Falhas: %{customdata[4]}<br>%{customdata[5]}<extra></extra>'}],layout);
    }
  }
  const audit=[...data.annual,...data.monthly];
  $('maintenance-audit').innerHTML=audit.map(r=>{
    const notes=[...(r.errors||[])];
    if(r.partial)notes.push('Período parcial');
    if(r.months_with_data!==undefined)notes.push(`${r.months_with_data} mês(es) com dados`);
    if(r.overlaps)notes.push(`${r.overlaps} lançamento(s) com sobreposição`);
    if(r.zero_duration)notes.push(`${r.zero_duration} lançamento(s) com início igual ao fim e minutos positivos`);
    if(!r.failures&&r.records)notes.push('Sem eventos de falha: MTBF e MTTR indisponíveis');
    const coverage=r.coverage.map(c=>`${dateText(c.from+'T00:00:00')}–${dateText(c.to+'T00:00:00')}`).join('; ');
    return `<tr><td><strong>${esc(r.period)}</strong><small>${esc(coverage||'Sem cobertura')}</small></td><td>${fmt(r.calendar_hours,2)}</td>${meta.modalities.map(m=>`<td>${fmt(r.modalities[m],2)}</td>`).join('')}<td>${fmt(r.failures)}</td><td>${r.failure_events===null?'—':fmt(r.failure_events,r.months_with_data===undefined?0:2)}</td><td class="audit-notes">${esc(notes.join(' · ')||'—')}</td></tr>`;
  }).join('');
}
$('maintenance-form').addEventListener('submit',run(async e=>{e.preventDefault();await loadMaintenance();}));
$('maintenance-equipment').addEventListener('change',run(loadMaintenance));
$('targets-form').addEventListener('submit',run(async e=>{
  e.preventDefault();
  if(!maintenanceData||maintenanceData.equipment!==$('maintenance-equipment').value)throw new Error('Atualize os indicadores da linha antes de salvar as metas.');
  const equipment=maintenanceData.equipment,targets={};
  Object.keys(maintenanceSpecs).forEach(key=>targets[key]=$('target-'+key).value===''?null:Number($('target-'+key).value));
  $('targets-fields').disabled=true;
  try{
    const result=await api('/api/maintenance/targets',{equipment,targets});
    if(maintenanceData.equipment===equipment){maintenanceData.targets=result.targets;renderMaintenance();}
    toast('Metas salvas para a linha '+equipment+'.');
  }finally{$('targets-fields').disabled=false;}
}));
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',run(()=>showView(b.dataset.view))));
$('filters-form').addEventListener('submit',run(async e=>{e.preventDefault();filters=readFilters();page=1;clearSelection();writeFilters();await refreshView();}));
$('clear-filters').addEventListener('click',run(async()=>{filters={};page=1;clearSelection();writeFilters();await refreshView();}));
['metric','pareto-metric','pareto-labels','heatmap-metric','heatmap-group'].forEach(id=>$(id).addEventListener('change',renderCharts));$('stack').addEventListener('change',run(loadSummary));
$('classify-unassigned').addEventListener('click',run(()=>drill({offender:['none']})));
$('previous-page').addEventListener('click',run(async()=>{page--;await loadRecords();}));
$('next-page').addEventListener('click',run(async()=>{page++;await loadRecords();}));
$('select-page').addEventListener('change',()=>{if(allFiltered)allFiltered=false;recordData.rows.forEach(r=>$('select-page').checked?selected.add(r.id):selected.delete(r.id));updateSelection();});
$('select-all-results').addEventListener('click',()=>{allFiltered=true;selected.clear();updateSelection();});
$('clear-selection').addEventListener('click',clearSelection);
$('assign-offender').addEventListener('click',run(()=>bulkClassify('offender_id')));
$('assign-type').addEventListener('click',run(()=>bulkClassify('type_override')));
$('records-body').addEventListener('change',run(async e=>{
  if(e.target.matches('.record-check')) {if(allFiltered){allFiltered=false;selected=new Set(recordData.rows.map(r=>r.id));}e.target.checked?selected.add(e.target.dataset.id):selected.delete(e.target.dataset.id);updateSelection();}
  if(e.target.matches('.row-offender')) {e.target.disabled=true;try{await api('/api/classify',{ids:[e.target.dataset.id],value:e.target.value||null});toast('Ofensor atualizado.');clearSelection();await loadRecords();}catch(error){await loadRecords();throw error;}}
}));
$('records-body').addEventListener('click',run(async e=>{const b=e.target.closest('.detail-button');if(b)await showDetail(b.dataset.id);}));
$('new-offender').addEventListener('click',()=>{createFromRecords=false;openOffender();});
$('new-offender-quick').addEventListener('click',()=>{createFromRecords=true;openOffender();});
document.querySelectorAll('.close-dialog').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$('offender-form').addEventListener('submit',run(async e=>{
  e.preventDefault();const result=await api('/api/offenders',{id:$('offender-id').value||null,name:$('offender-name').value,description:$('offender-description').value,color:$('offender-color').value,equipment:[...$('offender-equipment').selectedOptions].map(o=>o.value)});
  $('offender-dialog').close();await loadMeta();if(createFromRecords)$('bulk-offender').value=result.id;
  toast(createFromRecords?'Ofensor criado. Clique em Aplicar ofensor para classificar os selecionados.':'Ofensor salvo.');
  if(currentView==='records')await loadRecords();
}));
$('offenders-list').addEventListener('click',run(async e=>{
  const edit=e.target.closest('.offender-edit'),view=e.target.closest('.offender-view');
  if(edit){createFromRecords=false;openOffender(Number(edit.dataset.id));}
  if(view){filters={...filters,offender:[view.dataset.id]};writeFilters();await showView('dashboard');}
}));
$('select-local-all').addEventListener('click',()=>{document.querySelectorAll('.local-file').forEach(e=>e.checked=true);});
$('import-local').addEventListener('click',run(async()=>{const names=[...document.querySelectorAll('.local-file:checked')].map(e=>e.value);await api('/api/import/local',{names});setImportBusy(true);await pollImport();}));
$('import-upload').addEventListener('click',run(async()=>{const data=new FormData();for(const file of $('uploads').files)data.append('files',file);await api('/api/import/upload',data);setImportBusy(true);await pollImport();}));
$('files-body').addEventListener('click',run(async e=>{const b=e.target.closest('.file-issues');if(!b)return;const result=await api(`/api/files/${b.dataset.id}/issues`);$('issues-content').innerHTML=`<p>${fmt(result.invalid)} linha(s) inválida(s). A lista guarda até 2.000 erros de linha por arquivo.</p>`+(result.issues.length?'<ul>'+result.issues.map(i=>`<li>${esc(i.sheet)}, linha ${i.row}: ${esc(i.error)}</li>`).join('')+'</ul>':'<p>Nenhum erro de importação encontrado.</p>');$('issues-dialog').showModal();}));
$('settings-form').addEventListener('submit',run(async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await api('/api/settings',{tolerance:$('tolerance').value});await loadMeta();toast('Tolerância salva e eventos reagrupados.');}finally{button.disabled=false;}}));
$('export').addEventListener('click',run(async()=>{const response=await api('/api/export',filters,true),blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='paradas_filtradas.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Exportação concluída.');}));
window.addEventListener('resize',()=>{document.querySelectorAll('.view:not([hidden]) .chart').forEach(c=>{if(c.data)Plotly.Plots.resize(c);});});
window.addEventListener('popstate',run(()=>showView(location.pathname==='/kpi-manutencao'?'maintenance':'dashboard')));
run(async()=>{await loadMeta();if(meta.year.length)filters.year=[meta.year.at(-1)];writeFilters();await showView(location.pathname==='/kpi-manutencao'?'maintenance':meta.files.length?'dashboard':'files');await pollImport();})();
