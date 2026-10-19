/* Account-scoped CSV review and durable Cloud batches. */
(() => {
  'use strict';
  const finalStates = new Set(['completed','completed_with_errors','cancelled']);
  let generation=0, timer=null, serial=0;
  let rows=[], jobs=[], current=null, createKey=null, retryKey=null, busy=false;
  const active=()=>activeAccountId!=='guest'&&cloudAccount?.authenticated;
  const visible=()=>$('#view-batches').classList.contains('active');
  const statusLabel=value=>tr(({queued:'Waiting',running:'Processing',completed:'Completed',completed_with_errors:'Completed with errors',failed:'Failed',cancelling:'Cancelling',cancelled:'Cancelled'})[value]||value);
  const feedback=message=>{$('#batchFeedback').textContent=message;};
  const validContext=(account,version)=>account===activeAccountId&&version===generation;
  const errorMessages={
    csv_too_large:'The CSV exceeds 2 MB.',csv_requires_utf8:'Save the CSV using UTF-8 encoding.',
    invalid_csv:'The CSV could not be read. Check quotes and separators.',
    duplicate_csv_columns:'The CSV has duplicate columns.',unknown_csv_columns:'The CSV has unsupported columns. Use the template headers.',
    product_name_column_required:'The product_name column is required.',csv_too_many_rows:'Use at most 50 products per CSV.',
    csv_has_no_products:'The CSV contains no products.',batch_still_active:'Cancel or finish the batch before deleting it.',batch_already_active:'Finish or cancel the active batch before starting another.',
    device_not_authorized:'Sign out and sign in again to authorize this device.',cloud_unavailable:'Cloud unavailable. Try again.',
    analysis_timeout:'The product analysis timed out.',analysis_failed:'The product could not be analyzed. Retry it.',
    account_unavailable:'The account is unavailable.',authentication_required:'Sign in to continue.'
  };
  async function request(url,options={}){
    const response=await fetch(url,options);let data={};try{data=await response.json()}catch{}
    if(!response.ok){
      if(response.status===404)throw new Error(tr('This batch is unavailable or the Cloud needs updating.'));
      const code=typeof data.detail==='string'?data.detail:'';
      throw new Error(tr(errorMessages[code]||'Request failed. Review the product fields and try again.'));
    }
    return data;
  }
  function updateButtons(){
    const count=$$('#batchPreviewRows input:checked:not(:disabled)').length;
    $('#batchStart').disabled=busy||!count||jobs.some(job=>!finalStates.has(job.status));
    $('#batchPreviewButton').disabled=busy;
    $('#batchCancel').disabled=busy||!current||finalStates.has(current.status)||current.status==='cancelling';
    $('#batchRetry').disabled=busy||!current||!finalStates.has(current.status)||!current.rows.some(row=>row.status==='failed');
    $('#batchExport').disabled=busy||!current;
    $('#batchDelete').disabled=busy||!current||!finalStates.has(current.status);
  }
  function renderPreview(){
    const checks=$$('#batchPreviewRows input');
    const selected=checks.length?new Set(checks.filter(x=>x.checked).map(x=>Number(x.dataset.batchRow))):null;
    $('#batchPreviewPanel').hidden=!rows.length;
    $('#batchPreviewRows').innerHTML=rows.map((row,index)=>`<tr><td><input type="checkbox" data-batch-row="${index}" ${!row.valid?'disabled':!selected||selected.has(index)?'checked':''} aria-label="${escapeAttr(tr('Select product'))}"></td><td>${row.line}</td><td>${escapeHtml(row.fields.product_name||'—')}<small>${escapeHtml(row.fields.sku||'')}</small></td><td>${escapeHtml(row.fields.variant_text||'—')}</td><td>${row.valid?fmtMoney(row.fields.purchase_cost,row.fields.purchase_currency):escapeHtml(row.fields.purchase_cost||'—')}</td><td>${escapeHtml(row.fields.destination_country||'BR')}</td><td>${row.valid?`${Number(row.fields.marketplace_fee_percent+row.fields.taxes_percent+row.fields.ads_percent).toLocaleString(appLocale())}% / ${Number(row.fields.desired_margin_percent).toLocaleString(appLocale())}%`:'—'}</td><td>${row.valid?escapeHtml(tr('Ready')):row.errors.map(error=>`${escapeHtml(error.field)}: ${escapeHtml(tr(error.code==='column_count_mismatch'?'Column count does not match the header.':error.code==='missing'?'Required value.':'Check the value, currency, country and fee limits.'))}`).join('<br>')}</td></tr>`).join('');
    $$('#batchPreviewRows input').forEach(input=>input.addEventListener('change',()=>{createKey=null;updateButtons()}));
    updateButtons();
  }
  function renderJob(job){
    if(current?.id!==job.id)retryKey=null;
    current=job;
    const index=jobs.findIndex(x=>x.id===job.id);if(index>=0)jobs[index]=job;else jobs.push(job);
    const option=[...$('#batchSelect').options].find(x=>x.value===job.id);
    if(option)option.textContent=`${new Date(job.created_at).toLocaleString(appLocale())} · ${statusLabel(job.status)} · ${job.total}`;
    const done=job.counts.completed+job.counts.failed+job.counts.cancelled;
    $('#batchProgress').textContent=`${statusLabel(job.status)} · ${done}/${job.total} · ${tr('Completed')}: ${job.counts.completed} · ${tr('Failed')}: ${job.counts.failed} · ${tr('Cancelled')}: ${job.counts.cancelled}`;
    $('#batchProgressBar').max=Math.max(1,job.total);$('#batchProgressBar').value=done;
    $('#batchResultRows').innerHTML=job.rows.map(row=>{
      const summary=row.summary;
      return `<tr><td>${row.line}</td><td>${escapeHtml(row.fields.product_name)}<small>${escapeHtml([row.fields.sku,row.fields.variant_text].filter(Boolean).join(' · '))}</small></td><td>${escapeHtml(statusLabel(row.status))}${row.error_code?`<small>${escapeHtml(tr(errorMessages[row.error_code]||'The product could not be analyzed. Retry it.'))}</small>`:''}</td><td>${summary.quality?escapeHtml(tr(historyModeLabel(summary.quality))):'—'}</td><td>${summary.recommended_price==null?'—':fmtBRL(summary.recommended_price)}</td><td>${summary.net_margin_percent==null?'—':Number(summary.net_margin_percent).toLocaleString(appLocale())+'%'}</td><td>${row.analysis_id?`<button class="ghost batch-open" data-id="${escapeAttr(row.analysis_id)}">${escapeHtml(tr('Open analysis'))}</button>`:''}</td></tr>`;
    }).join('');
    $$('.batch-open').forEach(button=>button.addEventListener('click',()=>openSavedAnalysis(button.dataset.id)));
    updateButtons();
  }
  function stopPoll(){if(timer)clearTimeout(timer);timer=null;}
  function schedule(){
    stopPoll();
    if(active()&&visible()&&current&&!finalStates.has(current.status))timer=setTimeout(()=>refreshJob(current.id),2500);
  }
  async function refreshJob(id){
    stopPoll();const account=activeAccountId,version=generation,ticket=++serial;
    try{
      const job=await request('/api/batches/'+encodeURIComponent(id));
      if(!validContext(account,version)||ticket!==serial)return;
      const previous=current?.status;renderJob(job);
      const index=jobs.findIndex(x=>x.id===job.id);if(index>=0)jobs[index]=job;
      if(finalStates.has(job.status)&&previous&&!finalStates.has(previous))syncAccountData(true);
    }catch(error){if(validContext(account,version)&&ticket===serial)$('#batchProgress').textContent=error.message;}
    finally{if(validContext(account,version)&&ticket===serial)schedule();}
  }
  async function load(){
    if(!active())return;stopPoll();
    const account=activeAccountId,version=generation;
    try{
      const data=await request('/api/batches');if(!validContext(account,version))return;
      jobs=data.items;
      const selected=jobs.some(job=>job.id===current?.id)?current.id:jobs[0]?.id;
      $('#batchSelect').innerHTML=`<option value="">${escapeHtml(tr('Select a batch'))}</option>`+jobs.map(job=>`<option value="${escapeAttr(job.id)}">${escapeHtml(new Date(job.created_at).toLocaleString(appLocale()))} · ${escapeHtml(statusLabel(job.status))} · ${job.total}</option>`).join('');
      if(selected){$('#batchSelect').value=selected;await refreshJob(selected)}else{current=null;$('#batchResultRows').innerHTML='';$('#batchProgressBar').value=0;$('#batchProgress').textContent=tr('No batches yet. Review a CSV to begin.');}
      updateButtons();
    }catch(error){if(validContext(account,version))$('#batchProgress').textContent=error.message;}
  }
  async function submitRows(selected,key){
    const account=activeAccountId,version=generation;busy=true;updateButtons();feedback(tr('Submitting batch…'));
    try{
      const job=await request('/api/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:key,rows:selected})});
      if(!validContext(account,version))return;
      createKey=null;renderJob(job);feedback(tr('Batch saved to your account. You can close the Desktop while it processes.'));await load();
    }catch(error){if(validContext(account,version))feedback(error.message)}
    finally{if(validContext(account,version)){busy=false;updateButtons();schedule()}}
  }
  $('#batchFile').addEventListener('change',()=>{rows=[];createKey=null;renderPreview();feedback('')});
  $('#batchPreviewButton').addEventListener('click',async()=>{
    const file=$('#batchFile').files?.[0];if(!file){feedback(tr('Choose a CSV file first.'));return;}
    if(file.size>2*1024*1024){feedback(tr(errorMessages.csv_too_large));return;}
    const account=activeAccountId,version=generation;busy=true;updateButtons();feedback(tr('Reviewing CSV…'));
    try{
      const formData=new FormData();formData.append('file',file);
      const data=await request('/api/batches/preview',{method:'POST',body:formData});
      if(!validContext(account,version))return;
      rows=data.rows;createKey=null;renderPreview();feedback(`${tr('Ready')}: ${data.valid_count} · ${tr('Invalid')}: ${data.invalid_count}. ${tr('Only selected valid products will be analyzed.')}`);
    }catch(error){if(validContext(account,version)){rows=[];renderPreview();feedback(error.message)}}
    finally{if(validContext(account,version)){busy=false;updateButtons()}}
  });
  $('#batchStart').addEventListener('click',()=>{
    const selected=$$('#batchPreviewRows input:checked:not(:disabled)').map(input=>rows[Number(input.dataset.batchRow)]).map(row=>({line:row.line,fields:row.fields}));
    if(!selected.length)return;
    createKey=createKey||crypto.randomUUID();submitRows(selected,createKey);
  });
  $('#batchSelect').addEventListener('change',()=>{
    const id=$('#batchSelect').value;
    if(id){retryKey=null;refreshJob(id)}else{stopPoll();++serial;current=null;$('#batchResultRows').innerHTML='';$('#batchProgress').textContent='';updateButtons()}
  });
  $('#batchRefresh').addEventListener('click',load);
  $('#batchCancel').addEventListener('click',async()=>{
    if(!current||!confirm(tr('Cancel waiting products? The current product can finish.')))return;
    const account=activeAccountId,version=generation;busy=true;updateButtons();
    try{const job=await request(`/api/batches/${encodeURIComponent(current.id)}/cancel`,{method:'POST'});if(validContext(account,version)){renderJob(job);await load()}}catch(error){if(validContext(account,version))feedback(error.message)}finally{if(validContext(account,version)){busy=false;updateButtons()}}
  });
  $('#batchRetry').addEventListener('click',()=>{
    const selected=current?.rows.filter(row=>row.status==='failed').map(row=>({line:row.line,fields:row.fields}));
    if(!selected?.length)return;
    retryKey=retryKey||crypto.randomUUID();submitRows(selected,retryKey);
  });
  $('#batchExport').addEventListener('click',async()=>{
    if(!current)return;const account=activeAccountId,version=generation,id=current.id;
    try{
      const response=await fetch(`/api/batches/${encodeURIComponent(id)}/export`);if(!response.ok)throw new Error(tr('Could not export batch results.'));
      const blob=await response.blob();if(!validContext(account,version))return;
      const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=`MarketAI-batch-${id}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){if(validContext(account,version))feedback(error.message)}
  });
  $('#batchDelete').addEventListener('click',async()=>{
    if(!current||!confirm(tr('Delete this batch? Its saved analyses remain in History.')))return;
    const account=activeAccountId,version=generation,id=current.id;busy=true;updateButtons();
    try{
      await request('/api/batches/'+encodeURIComponent(id),{method:'DELETE'});
      if(!validContext(account,version))return;
      current=null;await load();
    }catch(error){if(validContext(account,version))feedback(error.message)}finally{if(validContext(account,version)){busy=false;updateButtons()}}
  });
  function reset(){
    ++generation;++serial;stopPoll();rows=[];jobs=[];current=null;createKey=null;retryKey=null;busy=false;
    $('#batchFile').value='';$('#batchPreviewRows').innerHTML='';$('#batchPreviewPanel').hidden=true;$('#batchResultRows').innerHTML='';
    $('#batchSelect').innerHTML=`<option value="">${escapeHtml(tr('Select a batch'))}</option>`;$('#batchProgress').textContent='';$('#batchProgressBar').value=0;feedback('');updateButtons();
  }
  document.addEventListener('marketai:languagechange',()=>{if(rows.length)renderPreview();if(current)renderJob(current);if(active()&&visible())load()});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&active()&&visible())load()});
  window.MarketBatches={load,reset};
})();
