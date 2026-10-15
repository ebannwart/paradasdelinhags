(() => {
  const $=id=>document.getElementById('oa-'+id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const date=v=>v?v.slice(0,10).split('-').reverse().join('/'):'—';
  const done=a=>a.state.startsWith('Concluída');
  let data={notes:[],offenders:[]},page=1,version=0;
  async function api(url,body){
    const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(body)});
    const d=await r.json();if(!r.ok)throw Error(d.error||'Falha ao carregar vínculos.');return d;
  }
  const safe=fn=>async(...args)=>{try{await fn(...args);}catch(e){$('message').textContent=e.message;}};
  window.loadOffenderActions=async()=>{
    const request=++version,selected=$('offender').value,line=$('line').value;
    $('message').textContent='Carregando análises e ações…';
    const result=await api('/api/offender-actions'+(selected?'?offender='+encodeURIComponent(selected):''));
    if(request!==version)return;
    data=result;page=1;
    $('offender').innerHTML='<option value="">Selecione um ofensor</option>'+data.offenders.map(o=>`<option value="${o.id}">${esc(o.name)}</option>`).join('');
    $('offender').value=selected;
    const units=new Map(data.notes.map(n=>[n.line,n.unit]));
    $('line').innerHTML='<option value="">Todas as linhas</option>'+[...units].sort().map(([k,v])=>`<option value="${esc(k)}">${esc(v)}</option>`).join('');
    $('line').value=units.has(line)?line:'';
    $('source').textContent=data.snapshot?`Status da última importação: ${data.snapshot.name} · ${new Date(data.snapshot.imported_at).toLocaleString('pt-BR')}. Os vínculos automáticos são recalculados pela linha, data e hora a cada atualização.`:'Selecione um ofensor. Se não houver análises, importe o ZPMX em Configurações.';
    $('message').textContent='';render();
  };
  function matchesAction(a){
    const status=$('status').value;
    return !status||(status==='Concluídas'&&done(a))||(status==='Vencidas'&&a.state==='Vencida')||(status==='Abertas'&&(a.state.startsWith('Aberta')||a.state==='Vencida'))||(status==='Não identificado'&&a.state==='Status não identificado');
  }
  function render(){
    const mode=$('mode').value,line=$('line').value,q=norm($('search').value);
    const linked=data.notes.filter(n=>n.linked&&(!line||n.line===line));
    const current=linked.filter(n=>!n.stale).flatMap(n=>n.actions);
    $('summary').textContent=`${linked.length} ocorrências vinculadas (${linked.filter(n=>n.actions.length>0).length} com ações) · ${current.length} ações na importação atual · ${current.filter(done).length} concluídas · ${current.filter(a=>a.state.startsWith('Aberta')||a.state==='Vencida').length} abertas (${current.filter(a=>a.state==='Vencida').length} vencidas) · ${current.filter(a=>a.state==='Status não identificado').length} com status não identificado · ${linked.filter(n=>n.stale).length} notas ausentes da última importação. Resumo por ofensor e linha, sem filtro de busca/status.`;
    const notes=data.notes.filter(n=>(mode==='all'||(mode==='linked'?(n.linked&&n.actions.length>0):n.suggested))&&(!line||n.line===line)&&(!$('status').value||n.actions.some(matchesAction))&&(!q||norm([n.id,n.description,n.asset,...n.actions.flatMap(a=>[a.text,a.owner,a.owner_code])].join(' ')).includes(q))).sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id));
    const pages=Math.max(1,Math.ceil(notes.length/15));page=Math.min(page,pages);
    $('page').textContent=`${notes.length} análises · Página ${page} de ${pages}`;$('prev').disabled=page===1;$('next').disabled=page===pages;
    $('results').innerHTML=notes.slice((page-1)*15,page*15).map(n=>`<article class="panel padded oa-note">
      <div class="section-line"><h2>Nota ${esc(n.id)} · ${esc(n.description)}</h2><strong>${n.automatic?'Vínculo automático':n.manual_linked?'Vínculo manual anterior':'Sem correspondência automática'}</strong></div>
      <p>${esc(n.equipment||n.unit)} · Parada: ${date(n.date)} ${esc(n.time||'Horário não informado')} · Local: ${esc(n.asset)} · ${esc(n.analysis_state)}</p>
      <p class="field-help">${n.automatic?'Mesma linha e início da falha dentro do intervalo do lançamento abaixo.':n.manual_linked?'Vínculo manual preservado do cadastro anterior.':!n.time?'A exportação desta análise não contém o horário da parada.':'Nenhum lançamento deste ofensor contém o início da falha na mesma linha.'}</p>
      ${n.stale?'<p class="notice warning">Nota ausente da última importação. As ações abaixo são históricas, de '+date(n.source_imported_at)+', e não entram no resumo de status atuais.</p>':''}
      ${n.evidence.length?`<details><summary>${n.evidence.length} lançamento(s) correspondente(s) por linha, data e hora</summary>${n.evidence.map(r=>`<p>${date(r.start)} ${esc(r.start.slice(11,19))} até ${date(r.end)} ${esc(r.end.slice(11,19))} · ${esc(r.equipment)} · ${esc(r.minutes)} min · ${esc(r.reason)} — ${esc(r.observation)} <button type="button" class="text-button" data-record="${esc(r.id)}">Ver lançamento</button></p>`).join('')}</details>`:''}
      <details><summary>Análise e causas</summary>${n.investigations.map(i=>`<p><strong>${esc(i.symptom)}</strong><br>${esc(i.cause)}<br>${i.why.filter(Boolean).map(esc).join(' → ')}</p>`).join('')||'<p>Sem causa registrada na exportação.</p>'}</details>
      <div class="table-wrap"><table><thead><tr><th>Medida</th><th>Ação</th><th>Responsável</th><th>Prazo</th><th>Conclusão</th><th>Status atual / SAP</th></tr></thead><tbody>${n.actions.filter(matchesAction).map(a=>`<tr><td>${esc(a.item||'—')}</td><td>${esc(a.text)}</td><td>${esc(a.owner||a.owner_code||'—')}</td><td>${date(a.due)}</td><td>${date(a.completed)}</td><td><strong>${esc(a.state)}</strong><small>${esc(a.status)}</small></td></tr>`).join('')||'<tr><td colspan="6">Nenhuma ação registrada para este recorte.</td></tr>'}</tbody></table></div>
    </article>`).join('')||'<div class="panel padded"><p>'+(!$('offender').value?'Selecione um ofensor para consultar seu plano de ação.':mode==='linked'?'Nenhuma análise com ações corresponde aos horários dos lançamentos deste ofensor neste recorte. Confira o mapeamento de locais e linhas e a classificação dos lançamentos.':'Nenhuma análise encontrada neste recorte.')+'</p></div>';
  }
  const editMappingsRequested=new URLSearchParams(location.search).get('editar')==='locais';
  let mappingOptions=[];
  function addMapping(row={local:'',equipment:''}){
    const el=document.createElement('div');el.className='oa-mapping-row';
    el.innerHTML=`<label>Local SAP ou prefixo<input data-local list="oa-assets" required maxlength="160" value="${esc(row.local)}" placeholder="Ex.: G-CSN-79-002-023"></label><label>Linha de produção<select data-equipment required><option value="">Selecione</option>${mappingOptions.map(v=>`<option value="${esc(v)}" ${v===row.equipment?'selected':''}>${esc(v)}</option>`).join('')}</select></label><button type="button" class="button secondary" aria-label="Remover relação de local">Remover</button>`;
    el.querySelector('button').addEventListener('click',()=>el.remove());
    $('mapping-rows').appendChild(el);
  }
  async function openMappings(){
    const result=await api('/api/offender-actions/mappings');mappingOptions=result.equipment;
    $('mapping-rows').replaceChildren();$('mapping-message').textContent='';
    $('assets').innerHTML=result.assets.map(v=>`<option value="${esc(v)}"></option>`).join('');
    result.mappings.forEach(addMapping);if(!result.mappings.length)addMapping();
    $('mapping-dialog').showModal();
  }
  document.addEventListener('DOMContentLoaded',()=>{
    $('edit-mappings').addEventListener('click',safe(openMappings));
    $('add-mapping').addEventListener('click',()=>addMapping());
    $('cancel-mapping').addEventListener('click',()=>$('mapping-dialog').close());
    $('mapping-form').addEventListener('submit',async e=>{
      e.preventDefault();$('save-mapping').disabled=true;
      try{
        const mappings=[...$('mapping-rows').children].map(el=>({local:el.querySelector('[data-local]').value,equipment:el.querySelector('[data-equipment]').value}));
        await api('/api/offender-actions/mappings',{mappings});
        $('mapping-dialog').close();await window.loadOffenderActions();
        $('message').textContent='Relações salvas. Os vínculos automáticos foram recalculados.';
      }catch(err){if($('mapping-dialog').open)$('mapping-message').textContent=err.message;else $('message').textContent=err.message;}
      finally{$('save-mapping').disabled=false;}
    });
    if(editMappingsRequested)safe(openMappings)();
    $('offender').addEventListener('change',safe(window.loadOffenderActions));
    $('refresh').addEventListener('click',safe(window.loadOffenderActions));
    ['line','mode','status','search'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',()=>{page=1;render();}));
    $('prev').addEventListener('click',()=>{page--;render();});$('next').addEventListener('click',()=>{page++;render();});
    $('results').addEventListener('click',safe(async e=>{
      const record=e.target.closest('[data-record]');if(record){await showDetail(record.dataset.record);return;}

    }));
  });
})();
