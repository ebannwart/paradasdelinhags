'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => value ? value.slice(0,10).split('-').reverse().join('/') : 'Não informado';
const norm = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const monthName = value => new Date(`${value}-02T12:00:00`).toLocaleDateString('pt-BR',{month:'long',year:'numeric'});
const done = a => a.state === 'Concluída' || a.state === 'Concluída com atraso';
let data = {notes:[],history:[]}, tab = 'month', page = 1, requestNumber = 0, meetingKey = null, dirty = false;
let sortKey='date', sortDirection=-1;
const durationText=value=>value==null?'—':value.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const lossValue=note=>note.production_loss==null?'unknown':note.production_loss.toUpperCase()==='X'?'marked':note.production_loss===''?'unmarked':'unknown';
const lossText=note=>({marked:'Marcada (X)',unmarked:'Não marcada',unknown:'Não informada'})[lossValue(note)];
const columns=[['date','Data da parada'],['process_duration','Tempo parada'],['id','Nota'],['description','Ocorrência / local'],['unit','Linha'],['work_center','Centro trabalho'],['production_loss','Perda produção'],['analysis_state','Status análise'],['completed','Ações concluídas'],['overdue','Vencidas']];
function sortValue(note,key){
  if(key==='completed')return note.actions.filter(done).length;
  if(key==='overdue')return note.actions.filter(a=>a.state==='Vencida').length;
  if(key==='production_loss')return lossValue(note)==='unknown'?null:lossText(note);
  return note[key]??null;
}
function compareNotes(a,b){
  const av=sortValue(a,sortKey),bv=sortValue(b,sortKey);
  // Missing values remain last in both directions. Numeric durations sort numerically.
  if(av==null||av==='')return bv==null||bv===''?a.id.localeCompare(b.id):1;
  if(bv==null||bv==='')return -1;
  const result=typeof av==='number'?av-bv:String(av).localeCompare(String(bv),'pt-BR',{numeric:true});
  return result*sortDirection||a.id.localeCompare(b.id,'pt-BR',{numeric:true});
}
function message(text, error=false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
async function api(url, options={}) {
  const response = await fetch(url, {...options,headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content,...options.headers}});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a operação.');
  return result;
}
function badge(text) { return `<span class="badge ${text.includes('Vencida') ? 'red' : text.startsWith('Concluída') ? 'green' : text==='Em análise' ? 'blue' : ''}">${esc(text)}</span>`; }
function selectOptions(id, options, preferred) {
  $(id).innerHTML = options.map(([value,label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join('');
  if (options.some(([v])=>String(v)===String(preferred))) $(id).value = preferred;
}
async function load(snapshot='') {
  const ticket=++requestNumber;
  const result=await api('/api/failures/data'+(snapshot?'?snapshot='+encodeURIComponent(snapshot):''));
  if(ticket!==requestNumber)return;
  data=result;
  const oldLine=$('line').value, oldMonth=$('month').value;
  const lines=[...new Map(data.notes.map(n=>[n.line,n.unit])).entries()].sort((a,b)=>a[0].localeCompare(b[0]));
  const observed=[...new Set(data.notes.map(n=>n.date.slice(0,7)))].sort();
  const months=[];
  if(observed.length){
    const end=[observed[observed.length-1],data.today.slice(0,7)].sort().pop();
    let [y,m]=observed[0].split('-').map(Number);
    while(`${y}-${String(m).padStart(2,'0')}`<=end){months.push(`${y}-${String(m).padStart(2,'0')}`);if(++m===13){m=1;y++;}}
    months.reverse();
  }
  selectOptions('line',[['','Todas as linhas'],...lines],oldLine);
  const centers=[...new Set(data.notes.map(n=>n.work_center||''))].sort();
  selectOptions('work-center',[['','Todos'],...centers.filter(Boolean).map(c=>[c,c]),...(centers.includes('')?[['__missing','Não informado']]:[])],$('work-center').value);
  selectOptions('month',months.map(m=>[m,monthName(m)+(observed.includes(m)?'':' · sem ocorrências na base')]),oldMonth||observed[observed.length-1]);
  selectOptions('snapshot',data.history.map(s=>[s.id,`${date(s.imported_at)} · ${s.imported_at.slice(11,16)} · #${s.id}`]),data.selected);
  const source=data.history.find(s=>s.id===data.selected);
  $('source-info').textContent=source?`Base importada em ${date(source.imported_at)} às ${source.imported_at.slice(11,16)}`:'Importe o ZPMX para começar';
  $('snapshot-details').textContent=source?`${source.name} · ${data.notes.length.toLocaleString('pt-BR')} notas · ${data.rows.toLocaleString('pt-BR')} registros. Vencimentos em ${date(data.today)}.`:'Nenhuma importação salva.';
  $('quality-summary').textContent=`Qualidade da importação (${data.warnings.length} avisos)`;
  $('quality').innerHTML=(data.warnings.length?data.warnings.map(w=>`<p>${esc(w)}</p>`).join(''):'<p>Nenhuma inconsistência estrutural detectada.</p>')+(!data.extended?'<p>Exportação resumida: cinco porquês e identificadores podem estar ausentes.</p>':'')+(data.selected&&data.schema_version!==2?'<p>Versão anterior: centro de trabalho, perda de produção e tempo de processo não foram armazenados. Importe novamente o ZPMX para gerar uma versão completa.</p>':'');
  page=1; render();
  if(tab==='meeting')await loadMeeting();
}
function common(note) {
  const terms=norm($('search').value).trim().split(/\s+/).filter(Boolean);
  return (!$('line').value||note.line===$('line').value)&&(!$('analysis').value||note.analysis_state===$('analysis').value)&&
    (!$('work-center').value||($('work-center').value==='__missing'?!note.work_center:note.work_center===$('work-center').value))&&
    (!$('production-loss').value||lossValue(note)===$('production-loss').value)&&
    (!$('action').value||note.actions.some(a=>a.state===$('action').value))&&terms.every(t=>norm(`${note.id} ${note.description} ${note.asset}`).includes(t));
}
function filteredActions(note) {return note.actions.filter(a=>!$('action').value||a.state===$('action').value);}
function lists() {
  const month=$('month').value;
  const selected=data.notes.filter(common);
  const monthly=selected.filter(n=>n.date.startsWith(month));
  const backlog=selected.filter(n=>n.date.slice(0,7)<month&&(n.analysis_state==='Em análise'||n.actions.some(a=>!done(a))));
  const completed=selected.filter(n=>n.analysis_state==='Concluída'&&n.actions.every(done));
  monthly.sort(compareNotes);
  backlog.sort(compareNotes);
  completed.sort(compareNotes);
  selected.sort(compareNotes);
  return {monthly,backlog,completed,all:selected};
}
function activeRows(groups){return groups[{month:'monthly',backlog:'backlog',completed:'completed',all:'all',meeting:'monthly'}[tab]];}
function render() {
  const groups=lists(), {monthly,backlog,completed,all}=groups, rows=activeRows(groups);
  const actions=rows.flatMap(filteredActions), open=actions.filter(a=>!done(a));
  const metrics=[['Ocorrências',rows.length,'notas na aba e filtros atuais'],['Em análise',rows.filter(n=>n.analysis_state==='Em análise').length,'status da nota no SAP'],['Analisadas / concluídas',rows.filter(n=>['Falha analisada','Concluída'].includes(n.analysis_state)).length,'não implica ações encerradas'],['Ações abertas',open.length,'inclui status não identificado'],['Ações vencidas',actions.filter(a=>a.state==='Vencida').length,'das ocorrências desta aba']];
  $('metrics').innerHTML=metrics.map(([label,value,hint],i)=>`<article class="failure-metric ${i===4?'alert':''}"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`).join('');
  $('month-count').textContent=monthly.length;$('backlog-count').textContent=backlog.length;
  $('completed-count').textContent=completed.length;$('all-count').textContent=all.length;
  $('month').disabled=['completed','all'].includes(tab);
  $('month').title=$('month').disabled?'Esta aba considera todos os meses da importação.':'';
  $('metrics').setAttribute('aria-label','Resumo da aba selecionada');
  $('listing').hidden=tab==='meeting';$('meeting-panel').hidden=tab!=='meeting';
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('selected',b.dataset.tab===tab);b.setAttribute('aria-pressed',b.dataset.tab===tab);});
  $('list-title').textContent={month:'Ocorrências do mês',backlog:'Pendências de meses anteriores',completed:'Concluídas',all:'Todas as ocorrências',meeting:'Registro mensal'}[tab];
  $('list-help').textContent={month:`${monthly.filter(n=>n.analysis_state==='Dispensada').length} dispensadas de análise. Abra uma ocorrência para consultar a investigação e todas as ações.`,backlog:'Notas anteriores ao mês selecionado com análise em andamento ou ações não encerradas. Mesmos filtros aplicados.',completed:'Todos os meses: notas com análise concluída e sem ações em aberto. Notas concluídas sem ações registradas também aparecem. Demais filtros aplicados.',all:'Todas as ocorrências da importação selecionada, de todos os meses. Filtros de linha, centro de trabalho, perda de produção, status e busca continuam aplicados.',meeting:''}[tab];
  const pages=Math.max(1,Math.ceil(rows.length/(data.page_size||15)));page=Math.min(page,pages);
  const tableRows=rows.slice((page-1)*(data.page_size||15),page*(data.page_size||15)).map(n=>{
    const completed=n.actions.filter(done).length, overdue=n.actions.filter(a=>a.state==='Vencida').length;
    return `<tr><td class="date-cell">${date(n.date)}</td><td class="number-cell">${durationText(n.process_duration)}</td><td><button class="note-link" data-note="${esc(n.id)}">${esc(n.id)}</button></td><td class="description-cell"><button class="occurrence-title" data-note="${esc(n.id)}">${esc(n.description)}</button><div class="occurrence-sub">${esc(n.asset)}</div></td><td>${esc(n.unit)}</td><td>${esc(n.work_center||'Não informado')}</td><td>${esc(lossText(n))}</td><td>${badge(n.analysis_state)}</td><td class="number-cell">${completed} / ${n.actions.length}</td><td class="number-cell">${overdue?badge(`Vencida: ${overdue}`):'0'}</td></tr>`;
  }).join('');
  $('occurrences').innerHTML=`<div class="occurrence-table-scroll" tabindex="0" role="region" aria-label="Tabela de ocorrências ordenável"><table class="occurrence-table"><caption>Data: parada do processo · Tempo: duração do processo na unidade do ZPMX, ainda não confirmada. Clique nos títulos para ordenar.</caption><thead><tr>${columns.map(([key,label])=>`<th scope="col" aria-sort="${key===sortKey?(sortDirection===1?'ascending':'descending'):'none'}"><button data-sort="${key}" aria-label="Ordenar por ${label}">${label}<span aria-hidden="true"> ${key===sortKey?(sortDirection===1?'↑':'↓'):'↕'}</span></button></th>`).join('')}</tr></thead><tbody>${tableRows||`<tr><td colspan="10" class="empty">${data.notes.length?'Nenhuma ocorrência neste recorte. Ajuste os filtros.':'Importe o ZPMX para iniciar o acompanhamento.'}</td></tr>`}</tbody></table></div>`;
  $('pagination').innerHTML=rows.length>(data.page_size||15)?`<button class="button secondary" id="prev" ${page===1?'disabled':''}>Anterior</button><span>${page} de ${pages}</span><button class="button secondary" id="next" ${page===pages?'disabled':''}>Próxima</button>`:'';
  if($('prev'))$('prev').onclick=()=>{page--;render();};if($('next'))$('next').onclick=()=>{page++;render();};
  $('export').disabled=!rows.some(n=>filteredActions(n).length);
}
function showDetail(id) {
  const note=data.notes.find(n=>n.id===id);if(!note)return;
  // An action row often repeats the why chain without the object details.
  // Hide only these redundant, less complete copies in the presentation.
  const investigations=note.investigations.filter(inv=>!note.investigations.some(other=>other!==inv &&
    JSON.stringify(other.why)===JSON.stringify(inv.why) &&
    ['item','symptom','cause','order'].every(k=>!inv[k]||inv[k]===other[k]) &&
    ['item','symptom','cause','order'].some(k=>!inv[k]&&other[k])));
  $('detail-body').innerHTML=`<h2>${esc(note.description)}</h2><div class="detail-meta"><span>Nota <strong>${esc(note.id)}</strong></span><span>${esc(note.unit)}</span><span>Data da parada (processo): ${date(note.date)}</span><span>Tempo de parada (processo): ${durationText(note.process_duration)}</span><span>Centro de trabalho: ${esc(note.work_center||'Não informado')}</span><span>Perda de produção: ${esc(lossText(note))}</span><span>Duração de produção: ${note.duration==null?'Não informada':note.duration.toLocaleString('pt-BR',{maximumFractionDigits:2})} (unidade não confirmada)</span></div><p>${esc(note.asset)}</p><p>Status original: <strong>${esc(note.status)}</strong> · Responsável: ${esc(note.owner||'Não informado')} · Reabertura: ${esc(note.reopened||'Não informada')}</p><section class="detail-section"><h3>Investigação registrada</h3>${investigations.map(inv=>`<p>Item ${esc(inv.item||'não informado')} · Ordem ${esc(inv.order||'não informada')}<br>Sintoma: ${esc(inv.symptom||'Não informado')}<br>Causa provável: ${esc(inv.cause||'Não informada')}</p><div class="why-list">${inv.why.map((why,i)=>`<div class="why"><strong>Porquê ${i+1}</strong>${esc(why||'Não preenchido')}</div>`).join('')}</div>`).join('')||'<p>Investigação não preenchida nesta exportação.</p>'}</section><section class="detail-section"><h3>Ações da falha (${note.actions.length})</h3><div class="actions-scroll"><table class="actions-table"><thead><tr><th>Ação</th><th>Responsável</th><th>Prazo</th><th>Conclusão</th><th>Situação</th><th>Eficácia</th></tr></thead><tbody>${note.actions.map(a=>`<tr><td>${esc(a.text||'Sem descrição')}<div class="muted">Medida ${esc(a.item||'s/n')} · item ${esc(a.object_item||'s/n')}</div></td><td>${esc(a.owner||'Não informado')}</td><td>${date(a.due)}</td><td>${date(a.completed)}</td><td>${badge(a.state)}<div class="muted">SAP: ${esc(a.status||'Não informado')}</div></td><td>${esc(a.efficacy||'Não registrada')}${a.efficacy_status?`<br>${esc(a.efficacy_status)}`:''}</td></tr>`).join('')||'<tr><td colspan="6">Sem ações registradas no arquivo.</td></tr>'}</tbody></table></div></section><p class="detail-source">Fonte: ${esc(data.history.find(s=>s.id===data.selected)?.name)} · importação #${data.selected} · linhas ${note.sources.slice(0,15).join(', ')}${note.sources.length>15?'…':''}. Textos preservados conforme a exportação.</p>`;
  $('detail').showModal();
}
async function loadMeeting() {
  const line=$('line').value,month=$('month').value;meetingKey=null;
  $('meeting-text').disabled=true;$('save-meeting').disabled=true;$('meeting-text').value='';$('meeting-saved').textContent='';
  if(!line||!month){$('meeting-context').textContent='Selecione uma linha e um mês para registrar a reunião.';return;}
  const key=`${line}/${month}`;
  const result=await api(`/api/failures/meeting?line=${encodeURIComponent(line)}&month=${encodeURIComponent(month)}`);
  if(`${$('line').value}/${$('month').value}`!==key)return;
  meetingKey={line,month};dirty=false;
  $('meeting-context').textContent=`${$('line').selectedOptions[0].textContent} · ${monthName(month)}`;
  $('meeting-text').value=result.body;$('meeting-text').disabled=false;$('save-meeting').disabled=false;
  $('meeting-saved').textContent=result.updated_at?`Salvo em ${date(result.updated_at)} às ${result.updated_at.slice(11,16)}`:'Ainda sem registro.';
}
async function importData(file) {
  $('refresh-source').disabled=true;$('upload').disabled=true;message('Importando e conferindo as ocorrências…');
  try {const form=new FormData();if(file)form.append('file',file);const result=await api('/api/failures/import',{method:'POST',body:form});await load(result.id);message(result.unchanged?'Este arquivo já consta no histórico. Importação existente selecionada.':'Base importada. A versão anterior foi preservada.');}
  catch(error){message(error.message,true);}finally{$('refresh-source').disabled=false;$('upload').disabled=false;$('upload').value='';}
}
function csvExport() {
  const rows=activeRows(lists());
  const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
  const content=[['Nota','Linha','Data parada (processo)','Tempo parada (processo; unidade original)','Centro trabalho','Perda produção (marcação SAP)','Local','Falha','Status análise SAP','Item objeto','Medida','Ação','Responsável','Prazo','Conclusão','Status ação SAP','Situação em '+data.today,'Eficácia'],...rows.flatMap(n=>filteredActions(n).map(a=>[n.id,n.unit,n.date,n.process_duration,n.work_center,lossText(n),n.asset,n.description,n.status,a.object_item,a.item,a.text,a.owner,a.due,a.completed,a.status,a.state,a.efficacy]))].map(row=>row.map(cell).join(';')).join('\r\n');
  const url=URL.createObjectURL(new Blob(['\ufeff'+content],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`acoes-${$('line').value||'unidade'}-${['all','completed'].includes(tab)?'todos-meses':$('month').value}-${tab}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function safeRun(fn){return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(error=>message(error.message,true));}
for(const id of ['line','month','analysis','action','work-center','production-loss']) {
  $(id).addEventListener('focus',()=>{$(id).dataset.previous=$(id).value;});
  $(id).onchange=safeRun(async()=>{if(['line','month'].includes(id)&&dirty&&!confirm('Descartar alterações não salvas do registro mensal?')){$(id).value=$(id).dataset.previous;return;}if(['line','month'].includes(id))dirty=false;page=1;render();if(tab==='meeting'&&['line','month'].includes(id))await loadMeeting();});
}
$('search').oninput=()=>{page=1;render();};
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=safeRun(async()=>{if(button.dataset.tab===tab)return;if(dirty&&button.dataset.tab!=='meeting'&&!confirm('Descartar alterações não salvas do registro mensal?'))return;dirty=false;tab=button.dataset.tab;page=1;render();if(tab==='meeting')await loadMeeting();}));
$('occurrences').onclick=event=>{const sort=event.target.closest('[data-sort]');if(sort){if(sortKey===sort.dataset.sort)sortDirection*=-1;else{sortKey=sort.dataset.sort;sortDirection=1;}page=1;render();$('occurrences').querySelector(`[data-sort="${sortKey}"]`).focus({preventScroll:true});return;}const button=event.target.closest('[data-note]');if(button)showDetail(button.dataset.note);};
$('close-detail').onclick=()=>$('detail').close();
$('snapshot').onchange=safeRun(async()=>{if(dirty){$('snapshot').value=data.selected;message('Salve o registro mensal antes de trocar a importação.',true);return;}await load($('snapshot').value);});
$('refresh-source').onclick=()=>{if(dirty){message('Salve o registro mensal antes de importar.',true);return;}importData();};
$('upload').onchange=()=>{if(dirty){message('Salve o registro mensal antes de importar.',true);$('upload').value='';return;}if($('upload').files[0])importData($('upload').files[0]);};
$('meeting-text').oninput=()=>{dirty=true;};
$('save-meeting').onclick=safeRun(async()=>{if(!meetingKey)return;const key={...meetingKey},body=$('meeting-text').value;$('save-meeting').disabled=true;try{const result=await api('/api/failures/meeting',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...key,body})});if(meetingKey?.line===key.line&&meetingKey?.month===key.month){dirty=$('meeting-text').value!==body;$('meeting-saved').textContent=`Salvo em ${date(result.updated_at)} às ${result.updated_at.slice(11,16)}`;}message('Registro mensal salvo.');}finally{$('save-meeting').disabled=!meetingKey;}});
$('export').onclick=csvExport;
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
safeRun(load)();
