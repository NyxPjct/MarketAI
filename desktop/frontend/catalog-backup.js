/* Full account catalog archives with explicit review and revision-safe restore. */
(() => {
  'use strict';
  let generation=0, fileGeneration=0, busy=false, rows=[], digest='', file=null, pending=null, selectedRows=new Set();
  const feedback=message=>{$('#catalogBackupFeedback').textContent=message;};
  const valid=(account,version,upload)=>account===activeAccountId&&version===generation&&(upload==null||upload===fileGeneration);
  const messages={catalog_backup_invalid:'This catalog backup is invalid or uses an unsupported format.',
    catalog_backup_wrong_account:'This backup belongs to another account.',catalog_backup_too_large:'The complete catalog backup exceeds the processing limits.',
    catalog_backup_changed:'The file changed. Review the backup again.',catalog_restore_conflict:'The catalog or alert rules changed. Review the backup again.',
    catalog_restore_key_reused:'The restore selection changed. Review the backup again.',cloud_unavailable:'Cloud unavailable. Try again.'};
  async function checked(response){
    if(response.ok)return response;
    let data={};try{data=await response.json()}catch{}
    throw new Error(tr(messages[data.detail]||(response.status===404?'Catalog backup unavailable. Update the Cloud and try again.':'Could not process the catalog backup.')));
  }
  function buttons(){
    for(const id of ['#catalogBackupExport','#catalogBackupReview','#catalogBackupReplace'])$(id).disabled=busy;
    $$('#catalogBackupRows input').forEach(input=>input.disabled=busy||(rows[Number(input.dataset.restoreRow)].existing&&!$('#catalogBackupReplace').checked));
    $('#catalogBackupRestore').disabled=busy||!$$('#catalogBackupRows input:checked:not(:disabled)').length;
  }
  function render(){
    $('#catalogBackupPreview').hidden=!rows.length;
    $('#catalogBackupRows').innerHTML=rows.map((row,index)=>{
      const allowed=!row.existing||$('#catalogBackupReplace').checked;
      return `<tr><td><input type="checkbox" data-restore-row="${index}" ${allowed&&selectedRows.has(index)?'checked':''} ${allowed?'':'disabled'} aria-label="${escapeAttr(tr('Select product'))}"></td><td>${escapeHtml(row.fields.product_name)}<small>${escapeHtml(row.sku)}</small></td><td>${fmtMoney(row.fields.purchase_cost,row.fields.purchase_currency)}<small>${escapeHtml(tr('Stock'))}: ${row.stock}</small></td><td>${row.revisions}</td><td>${escapeHtml(tr(row.existing?'Replace only if selected':'Create product'))}</td></tr>`;
    }).join('');
    $$('#catalogBackupRows input').forEach(input=>input.addEventListener('change',()=>{
      const index=Number(input.dataset.restoreRow);if(input.checked)selectedRows.add(index);else selectedRows.delete(index);pending=null;buttons();
    }));buttons();
  }
  function clearFile(){
    ++fileGeneration;rows=[];selectedRows.clear();digest='';file=null;pending=null;busy=false;
    $('#catalogBackupRows').innerHTML='';$('#catalogBackupPreview').hidden=true;$('#catalogBackupReplace').checked=false;feedback('');buttons();
  }
  $('#catalogBackupFile').addEventListener('change',clearFile);
  $('#catalogBackupReplace').addEventListener('change',()=>{if(!$('#catalogBackupReplace').checked)for(const index of selectedRows)if(rows[index].existing)selectedRows.delete(index);pending=null;render()});
  $('#catalogBackupExport').addEventListener('click',async()=>{
    const account=activeAccountId,version=generation;busy=true;buttons();feedback(tr('Exporting complete catalog…'));
    try{
      const response=await checked(await fetch('/api/catalog/backup'));const blob=await response.blob();
      if(!valid(account,version))return;
      const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;
      link.download=`MarketAI-catalog-${new Date().toISOString().slice(0,10)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      feedback(tr('Complete catalog backup downloaded. Keep it in a safe place.'));
    }catch(error){if(valid(account,version))feedback(error.message)}finally{if(valid(account,version)){busy=false;buttons()}}
  });
  $('#catalogBackupReview').addEventListener('click',async()=>{
    const selectedFile=$('#catalogBackupFile').files?.[0];if(!selectedFile){feedback(tr('Choose a catalog backup file first.'));return;}
    if(selectedFile.size>10*1024*1024){feedback(tr(messages.catalog_backup_too_large));return;}
    const account=activeAccountId,version=generation,upload=fileGeneration;busy=true;buttons();feedback(tr('Reviewing catalog backup…'));
    try{
      const formData=new FormData();formData.append('file',selectedFile);
      const response=await checked(await fetch('/api/catalog/backup/preview',{method:'POST',body:formData}));const data=await response.json();
      if(!valid(account,version,upload))return;
      rows=data.items;selectedRows=new Set(rows.map((row,index)=>row.existing?-1:index).filter(index=>index>=0));digest=data.digest;file=selectedFile;pending=null;$('#catalogBackupRows').innerHTML='';$('#catalogBackupReplace').checked=false;render();
      feedback(rows.length?tr('Review the selection. Existing products remain unchanged unless selected for replacement.'):tr('This catalog backup contains no products.'));
    }catch(error){if(valid(account,version,upload)){rows=[];file=null;digest='';render();feedback(error.message)}}
    finally{if(valid(account,version,upload)){busy=false;buttons()}}
  });
  $('#catalogBackupRestore').addEventListener('click',async()=>{
    const selected=$$('#catalogBackupRows input:checked:not(:disabled)').map(input=>rows[Number(input.dataset.restoreRow)]);
    if(!selected.length||!file||busy)return;
    pending=pending||{client_id:crypto.randomUUID(),digest,products:selected.map(row=>({sku:row.sku,expected_id:row.expected_id,
      expected_revision:row.expected_revision,expected_watch_id:row.expected_watch_id,expected_rules_revision:row.expected_rules_revision}))};
    const account=activeAccountId,version=generation,upload=fileGeneration;busy=true;buttons();feedback(tr('Restoring catalog…'));
    try{
      const data=new FormData();data.append('file',file);data.append('plan',JSON.stringify(pending));
      const response=await checked(await fetch('/api/catalog/backup/restore',{method:'POST',body:data}));const result=await response.json();
      if(!valid(account,version,upload))return;
      rows=[];selectedRows.clear();file=null;pending=null;digest='';$('#catalogBackupFile').value='';render();
      feedback(`${tr('Created')}: ${result.created} · ${tr('Replaced')}: ${result.replaced} · ${tr('Revisions')}: ${result.revisions}. ${tr('Restored monitors are paused.')}`);
      window.MarketCatalog.refresh();syncAccountData(true);
    }catch(error){if(valid(account,version,upload))feedback(error.message)}finally{if(valid(account,version,upload)){busy=false;buttons()}}
  });
  function reset(){++generation;clearFile();$('#catalogBackupFile').value='';$('#catalogBackupPanel').open=false;}
  document.addEventListener('marketai:languagechange',()=>{
    // The shared translator updates labels; preserve the actual review controls.
    for(const [index,row] of rows.entries()){
      const cell=$$('#catalogBackupRows tr')[index]?.cells[2];
      if(cell)cell.innerHTML=`${fmtMoney(row.fields.purchase_cost,row.fields.purchase_currency)}<small>${escapeHtml(tr('Stock'))}: ${row.stock}</small>`;
    }
  });
  window.MarketCatalogBackup={reset};
})();
