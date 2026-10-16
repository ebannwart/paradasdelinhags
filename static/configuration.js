'use strict';
(() => {
const $=id=>document.getElementById(id), kinds=['IH06','IP18','IP24','IW39','IW49N'], indicators=['imc','dgfm','mtbf','mttr','failure_events'];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const planProfile=new URLSearchParams(location.search).get('profile')||'1';
let config, sap, stopTimer, planTimer, sourceDirty=new Set();
const message=(text,error=false)=>{$('config-message').textContent=text;$('config-message').classList.toggle('error',error);};
async function api(url,body){if(url.startsWith('/api/sap/')||url==='/api/configuration'||url==='/api/configuration/sources')url+='?profile='+encodeURIComponent(planProfile);const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Falha na operação.');return d;}
const run=fn=>async e=>{e?.preventDefault();try{await fn(e);}catch(error){message(error.message,true);}};
async function loadPlanProfiles(){
 const d=await api('/api/sap/profiles');
 $('plan-profile').innerHTML=d.profiles.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');
 $('plan-profile').value=planProfile;
 $('open-plan-profile').href='/plano-manutencao?profile='+encodeURIComponent(planProfile);
 $('plan-profile-name').value=d.profiles.find(p=>String(p.id)===planProfile)?.name||'';
}
$('plan-profile').onchange=()=>{location.href='/configuracoes?profile='+encodeURIComponent($('plan-profile').value)+'#preventivo';};
$('plan-profile-create').onclick=run(async()=>{
 const d=await api('/api/sap/profiles',{name:$('plan-profile-new-name').value});
 location.href='/configuracoes?profile='+d.id+'#preventivo';
});
$('plan-profile-rename').onclick=run(async()=>{
 await api('/api/sap/profiles',{id:Number(planProfile),name:$('plan-profile-name').value});
 await loadPlanProfiles();message('Nome da configuração atualizado.');
});
async function loadDatabaseSettings(){
 const d=await api('/api/configuration/database');
 $('database-active').textContent='Banco em uso: '+d.active;
 $('database-profile').textContent='Configuração local deste usuário: '+d.local_directory;
 $('database-path').value=d.selected;
 $('database-message').textContent=d.pending?'Alteração salva. Reinicie a aplicação para usar: '+d.selected:'';
}
$('database-form').onsubmit=run(async()=>{
 const button=$('database-form').querySelector('button');button.disabled=true;
 $('database-message').textContent='Validando o destino…';
 try{
  const result=await api('/api/configuration/database',{path:$('database-path').value,mode:$('database-mode').value});
  sourceDirty.delete('database');$('database-mode').value='existing';
  await loadDatabaseSettings();
  $('database-message').textContent=result.pending?'Endereço salvo. Feche e inicie a aplicação novamente para usar o banco escolhido.':'O banco escolhido já está em uso.';
 }catch(e){$('database-message').textContent=e.message;throw e;}
 finally{button.disabled=false;}
});
$('database-form').addEventListener('input',()=>sourceDirty.add('database'));
function status(path){return !path?'Não configurado':config.existence[path]?'Arquivo encontrado':'Arquivo ausente; confira o caminho ou coloque a exportação nesse endereço.';}
function addStop(path=''){
 const row=document.createElement('div');row.className='source-row';row.innerHTML=`<label>Arquivo de paradas (.xlsx)<input class="stop-path" list="source-options" value="${esc(path)}"><small class="${config.existence[path]?'source-ok':'source-missing'}">${esc(status(path))}</small></label><button type="button" class="text-button">Retirar da configuração</button>`;
 row.querySelector('button').onclick=()=>{row.remove();sourceDirty.add('stops');};$('stop-paths').append(row);
}
function renderSources(){
 $('directory').textContent=config.directory;$('source-options').innerHTML=config.available.map(p=>`<option value="${esc(p)}"></option>`).join('');
 $('stop-paths').innerHTML='';config.sources.stops.forEach(addStop);if(!config.sources.stops.length)addStop();
 $('failure-path').value=config.sources.failure;$('failure-status').textContent=status(config.sources.failure);$('failure-page-size').value=config.sources.failure_page_size;
 $('plan-paths').innerHTML=kinds.map(k=>`<label>${k}<input id="source-${k}" list="source-options" value="${esc(config.sources.plan[k]||'')}"><span class="field-help ${config.existence[config.sources.plan[k]]?'source-ok':'source-missing'}">${esc(status(config.sources.plan[k]))}</span></label>`).join('');
}
function showTargets(){const line=$('target-line').value;$('target-fields').disabled=!line;indicators.forEach(k=>{$('target-'+k).value=config.targets.find(t=>t.equipment===line&&t.indicator===k)?.value??'';});}
function renderGroups(){
 $('groups').innerHTML=sap.groups.map((g,i)=>`<div class="group-row"><strong>${esc(g.name)}</strong><label><input type="checkbox" data-visible="${g.id}" ${g.visible?'checked':''}> Exibir</label><button class="button secondary" data-edit="${g.id}">Editar</button><button class="button secondary" data-up="${g.id}" ${i===0?'disabled':''}>Subir</button><button class="button secondary" data-down="${g.id}" ${i===sap.groups.length-1?'disabled':''}>Descer</button><button class="text-button" data-delete="${g.id}">Excluir</button></div>`).join('')||'<p class="muted">Nenhum agrupamento configurado.</p>';
}
function groupEditor(group){$('group-id').value=group?.id||'';$('group-name').value=group?.name||'';const assets=new Map(sap.assets.map(a=>[a.asset,a.name]));for(const a of group?.assets||[])if(!assets.has(a))assets.set(a,a);$('group-assets').innerHTML=[...assets].map(([id,name])=>`<option value="${esc(id)}" ${group?.assets.includes(id)?'selected':''}>${esc(name)} · ${esc(id)}</option>`).join('');}
async function refreshImportInfo(){
 const current=await api('/api/configuration');config.files=current.files;config.equipment=current.equipment;config.targets=current.targets;
 $('stop-imported').innerHTML=config.files.map(f=>`<p><b>${esc(f.name)}</b> · ${f.row_count} registros · ${esc(f.imported_at)}</p>`).join('')||'<p>Nenhuma planilha importada.</p>';
 sap=await api('/api/sap/meta');$('plan-imported').innerHTML=sap.files.map(f=>`<p><b>${esc(f.kind)}</b> · ${esc(f.name)} · ${f.rows} registros</p>`).join('')||'<p>Nenhuma fonte SAP importada.</p>';
 renderGroups();
}
async function pollStops(){clearTimeout(stopTimer);const state=await api('/api/import/status');$('import-stops').disabled=state.running;$('tolerance-form').querySelector('button').disabled=state.running;$('stop-progress').innerHTML=state.total?`<strong>${state.running?'Importando '+esc(state.current):'Atualização finalizada'} · ${state.completed}/${state.total}</strong>`+state.results.map(r=>`<div>${esc(r.name)}: ${esc(r.status==='error'?r.error:r.status==='unchanged'?'sem alterações':'importado')}</div>`).join(''):'';if(state.running)stopTimer=setTimeout(run(pollStops),1500);else if(state.total)await refreshImportInfo();}
async function pollPlan(){clearTimeout(planTimer);const state=(await api('/api/sap/meta')).job;$('import-plan').disabled=state.running;$('plan-progress').textContent=state.running?'Importando fontes SAP…':state.error?'Falha: '+state.error:state.result?'Importação SAP concluída.':'';if(state.running)planTimer=setTimeout(run(pollPlan),1800);else if(state.result||state.error)await refreshImportInfo();}
async function saveSource(section,body){await api('/api/configuration/sources',{section,...body});sourceDirty.delete(section);const latest=await api('/api/configuration');config.sources=latest.sources;config.existence=latest.existence;
 if(section==='stops'){$('stop-paths').innerHTML='';config.sources.stops.forEach(addStop);}
 if(section==='failure')$('failure-path').value=config.sources.failure;
 if(section==='plan')for(const k of kinds){const input=$('source-'+k),hint=input.nextElementSibling;input.value=config.sources.plan[k]||'';hint.textContent=status(input.value);hint.className='field-help '+(config.existence[input.value]?'source-ok':'source-missing');}
 message('Configurações salvas. Serão usadas na próxima atualização.');}
for(const [form,section] of [['stops-form','stops'],['failure-form','failure'],['plan-form','plan']])$(form).addEventListener('input',()=>sourceDirty.add(section));
$('add-stop').onclick=()=>{addStop();sourceDirty.add('stops');};
$('stops-form').onsubmit=run(async()=>{await saveSource('stops',{paths:[...document.querySelectorAll('.stop-path')].map(e=>e.value).filter(v=>v.trim())});});
$('failure-form').onsubmit=run(async()=>{await saveSource('failure',{path:$('failure-path').value,page_size:Number($('failure-page-size').value)});$('failure-status').textContent=status(config.sources.failure);});
$('plan-form').onsubmit=run(async()=>{await saveSource('plan',{choices:Object.fromEntries(kinds.map(k=>[k,$('source-'+k).value]))});});
function requireSaved(section){if(sourceDirty.has(section))throw Error('Salve os caminhos desta seção antes de atualizar os dados.');}
$('import-stops').onclick=run(async()=>{requireSaved('stops');await api('/api/import/configured',{});await pollStops();});
$('import-failure').onclick=run(async()=>{requireSaved('failure');$('import-failure').disabled=true;try{const result=await api('/api/failures/import',{});message(result.unchanged?'O ZPMX já está atualizado.':'Análises de falha atualizadas; histórico preservado.');}finally{$('import-failure').disabled=false;}});
$('import-plan').onclick=run(async()=>{requireSaved('plan');await api('/api/sap/import',{});await pollPlan();});
$('tolerance-form').onsubmit=run(async()=>{await api('/api/settings',{tolerance:$('tolerance').value});message('Tolerância salva e eventos reagrupados.');});
$('target-line').onchange=showTargets;
$('targets-form').onsubmit=run(async()=>{const equipment=$('target-line').value;const targets=Object.fromEntries(indicators.map(k=>[k,$('target-'+k).value===''?null:Number($('target-'+k).value)]));await api('/api/maintenance/targets',{equipment,targets});config.targets=config.targets.filter(t=>t.equipment!==equipment).concat(Object.entries(targets).filter(([,v])=>v!==null).map(([indicator,value])=>({equipment,indicator,value})));message('Metas salvas para '+equipment+'.');});
$('rules-form').onsubmit=run(async()=>{const codes=id=>$(id).value.toUpperCase().split(/[\s,;]+/).filter(Boolean);const body={...sap.config,done_user:codes('done-user'),not_done_user:codes('not-done-user')};await api('/api/sap/config',body);sap.config=body;message('Regras do plano preventivo salvas.');});
$('group-new').onclick=()=>groupEditor();
$('group-form').onsubmit=run(async()=>{const id=$('group-id').value;await api('/api/sap/groups',{...(id?{id:Number(id)}:{}),name:$('group-name').value,assets:[...$('group-assets').selectedOptions].map(o=>o.value)});sap=await api('/api/sap/meta');renderGroups();groupEditor();message('Agrupamento salvo.');});
$('groups').onclick=run(async e=>{const button=e.target.closest('button');if(!button)return;const action=['edit','up','down','delete'].find(k=>button.dataset[k]);if(!action)return;const id=Number(button.dataset[action]),g=sap.groups.find(g=>g.id===id);if(action==='edit'){groupEditor(g);$('group-name').focus();return;}if(action==='delete'){if(!confirm(`Excluir o agrupamento “${g.name}”? Os ativos importados serão preservados.`))return;await api('/api/sap/groups/delete',{id});}else{const ids=sap.groups.map(g=>g.id),i=ids.indexOf(id),j=i+(action==='up'?-1:1);if(j<0||j>=ids.length)return;[ids[i],ids[j]]=[ids[j],ids[i]];await api('/api/sap/groups/reorder',{ids});}sap=await api('/api/sap/meta');renderGroups();});
$('groups').onchange=run(async e=>{if(e.target.dataset.visible){await api('/api/sap/groups/visibility',{id:Number(e.target.dataset.visible),visible:e.target.checked});sap=await api('/api/sap/meta');renderGroups();}});
window.addEventListener('beforeunload',e=>{if(sourceDirty.size){e.preventDefault();e.returnValue='';}});
run(async()=>{await loadDatabaseSettings();await loadPlanProfiles();config=await api('/api/configuration');renderSources();$('tolerance').value=config.tolerance;$('target-line').innerHTML=config.equipment.map(e=>`<option>${esc(e)}</option>`).join('');showTargets();await refreshImportInfo();$('done-user').value=sap.config.done_user.join(' ');$('not-done-user').value=sap.config.not_done_user.join(' ');groupEditor();await pollStops();await pollPlan();})();
})();
