/* Account catalog: revision-safe editing, trusted comparisons and bulk actions. */
(() => {
  'use strict';
  let generation=0,serial=0,offset=0,total=0,busy=false,editing=null,revisionProduct=null,revisionOffset=0;
  let products=[],selection=new Map(),pending=null,searchTimer=null;
  const defaults={sku:'',product_name:'',variant_text:'',supplier_name:'',purchase_cost:0,purchase_currency:'BRL',stock:0,quantity:1,
    origin_country:'CN',destination_country:'BR',freight_total:0,import_cost_total:0,packaging_unit:0,other_costs_unit:0,
    marketplace_fee_percent:16,taxes_percent:6,ads_percent:3,desired_margin_percent:20,match_mode:'strict',gtin:'',ncm:'',national_reference_cost:0};
  const labels={sku:'SKU',product_name:'Product name',variant_text:'Variant',supplier_name:'Supplier',purchase_cost:'Purchase cost',
    purchase_currency:'Currency',stock:'Stock',quantity:'Purchase quantity',origin_country:'Origin country',destination_country:'Destination country',
    freight_total:'Total freight',import_cost_total:'Total import costs',packaging_unit:'Packaging per unit',other_costs_unit:'Other costs per unit',
    marketplace_fee_percent:'Marketplace fee (%)',taxes_percent:'Taxes (%)',ads_percent:'Ads (%)',desired_margin_percent:'Target margin (%)',
    match_mode:'Matching mode',gtin:'GTIN / EAN / UPC',ncm:'NCM',national_reference_cost:'National reference cost'};
  const numeric=new Set(Object.keys(defaults).filter(key=>typeof defaults[key]==='number'));
  const active=()=>activeAccountId!=='guest'&&cloudAccount?.authenticated;
  const valid=(account,version)=>account===activeAccountId&&version===generation;
  const feedback=message=>{$('#catalogFeedback').textContent=message;};
  const errors={catalog_sku_exists:'A SKU already exists with different values. Edit it in the catalog.',duplicate_catalog_sku:'The selection contains duplicate SKUs.',
    catalog_revision_conflict:'This product changed on another device. Refresh and review it before trying again.',
    catalog_sku_immutable:'SKU cannot be changed. Add a separate product for a different SKU.',
    catalog_product_not_found:'This product is no longer available. Refresh the catalog.',
    batch_already_active:'Finish or cancel the active batch before starting another.',device_not_authorized:'Sign out and sign in again to authorize this device.',
    cloud_unavailable:'Cloud unavailable. Try again.',authentication_required:'Sign in to continue.'};
  async function request(url,options={}){
    const response=await fetch(url,options);let data={};try{data=await response.json()}catch{}
    if(!response.ok){
      if(response.status===404&&!errors[data.detail])throw new Error(tr('Catalog unavailable. Update the Cloud and try again.'));
      const fields=Array.isArray(data.detail)?[...new Set(data.detail.map(error=>labels[error.loc?.at(-1)]).filter(Boolean))].map(tr).join(', '):'';
      throw new Error(tr(errors[data.detail]||'Request failed. Review the product fields and try again.')+(fields?' '+fields:''));
    }
    return data;
  }
  const jsonOptions=(method,data)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const importProducts=items=>request('/api/catalog/import',jsonOptions('POST',{products:items}));
  function buttons(){
    $('#catalogSelected').textContent=`${tr('Selected')}: ${selection.size}`;
    for(const id of ['#catalogAnalyze','#catalogMonitor'])$(id).disabled=busy||!selection.size;
    for(const id of ['#catalogNew','#catalogRefresh','#catalogSave'])$(id).disabled=busy;
    $('#catalogPrevious').disabled=busy||offset===0;$('#catalogNext').disabled=busy||offset+50>=total;
    $('#catalogSelectAll').checked=products.length>0&&products.every(p=>selection.has(p.id));
    $('#catalogSelectAll').indeterminate=selection.size>0&&!$('#catalogSelectAll').checked;
    $('#catalogSelectAll').disabled=busy||!products.length;
    $$('#catalogRows button,#catalogRows input').forEach(el=>el.disabled=busy);
  }
  function clearSelection(){selection.clear();pending=null;}
  function render(){
    $('#catalogRows').innerHTML=products.map(product=>{
      const f=product.fields,latest=product.latest;
      return `<tr data-product-id="${escapeAttr(product.id)}"><td><input class="catalog-select" type="checkbox" ${selection.has(product.id)?'checked':''} aria-label="${escapeAttr(tr('Select product'))}"></td><td><strong>${escapeHtml(f.product_name)}</strong><small>${escapeHtml(f.sku)} · ${escapeHtml(f.variant_text||'—')}</small><small>${escapeHtml(f.supplier_name||'')}</small></td><td>${fmtMoney(f.purchase_cost,f.purchase_currency)}<small>${escapeHtml(tr('Stock'))}: ${product.stock.toLocaleString(appLocale())}</small></td><td>${latest?escapeHtml(tr(historyModeLabel(latest.quality))):'—'}${latest?.currency_fallback?`<small>${escapeHtml(tr('Fallback exchange rate'))}</small>`:''}</td><td>${fmtBRL(latest?.recommended_price)}</td><td>${latest?.net_margin_percent==null?'—':Number(latest.net_margin_percent).toLocaleString(appLocale())+'%'}</td><td>${fmtBRL(latest?.cost_floor)}</td><td>${latest?.collected_at?escapeHtml(new Date(latest.collected_at).toLocaleString(appLocale())):'—'}</td><td class="${latest?.outdated?'catalog-outdated':''}">${escapeHtml(tr(!latest?'Not analyzed':latest.outdated?'Inputs changed':'Matching current inputs'))}</td><td>${escapeHtml(tr(product.monitoring?'Enabled':'Inactive'))}</td><td><div class="catalog-row-actions"><button class="ghost catalog-edit">${escapeHtml(tr('Edit product'))}</button><button class="ghost catalog-history">${escapeHtml(tr('Change history'))}</button>${latest?`<button class="ghost catalog-open">${escapeHtml(tr('Open analysis'))}</button>`:''}<button class="ghost catalog-delete">${escapeHtml(tr('Delete product'))}</button></div></td></tr>`;
    }).join('')||`<tr><td colspan="11" class="empty">${escapeHtml(tr('No products match. Add a product or save a reviewed CSV selection.'))}</td></tr>`;
    for(const row of $$('#catalogRows tr[data-product-id]')){
      const product=products.find(p=>p.id===row.dataset.productId);
      row.querySelector('.catalog-select').addEventListener('change',event=>{
        if(event.target.checked)selection.set(product.id,{id:product.id,revision:product.revision});else selection.delete(product.id);
        pending=null;buttons();
      });
      row.querySelector('.catalog-edit').addEventListener('click',()=>editor(product));
      row.querySelector('.catalog-history').addEventListener('click',()=>{revisionProduct=product;revisionOffset=0;$('#catalogRevisions').showModal();loadRevisions()});
      row.querySelector('.catalog-open')?.addEventListener('click',()=>openSavedAnalysis(product.latest.analysis_id));
      row.querySelector('.catalog-delete').addEventListener('click',()=>remove(product));
    }
    $('#catalogPage').textContent=`${total?offset+1:0}–${Math.min(offset+50,total)} / ${total}`;
    buttons();
  }
  async function load(){
    if(!active())return;
    const account=activeAccountId,version=generation,ticket=++serial;
    const query=new URLSearchParams({q:$('#catalogSearch').value,quality:$('#catalogQuality').value,freshness:$('#catalogFreshness').value,sort:$('#catalogSort').value,offset});
    try{
      const data=await request('/api/catalog?'+query);
      if(!valid(account,version)||ticket!==serial)return;
      products=data.items;total=data.total;
      if(offset>=total&&offset>0){offset=Math.max(0,Math.floor((total-1)/50)*50);clearSelection();return load()}
      render();
    }catch(error){if(valid(account,version)&&ticket===serial)feedback(error.message)}
  }
  function editor(product=null){
    editing=product;
    const values=product?{...product.fields,stock:product.stock}:defaults;
    $('#catalogEditorTitle').textContent=tr(product?'Edit product':'Add product');$('#catalogEditorError').textContent='';
    $('#catalogFields').innerHTML=Object.keys(defaults).map(key=>{
      const source=form.elements[key];let control;
      if(source?.tagName==='SELECT')control=`<select name="${key}">${[...source.options].filter((option,index,all)=>all.findIndex(x=>x.value===option.value)===index).map(option=>`<option value="${escapeAttr(option.value)}" ${option.value===String(values[key])?'selected':''}>${escapeHtml(option.textContent)}</option>`).join('')}</select>`;
      else control=`<input name="${key}" ${numeric.has(key)?`type="number" min="0" max="${key==='stock'?1e9:key==='quantity'?1e6:key.endsWith('_percent')?99.999999:1e12}" step="${['stock','quantity'].includes(key)?1:'any'}"`:`type="text" maxlength="${key==='sku'?120:['gtin','ncm'].includes(key)?32:240}"`} value="${escapeAttr(values[key]??'')}" ${['sku','product_name'].includes(key)?'required':''} ${product&&key==='sku'?'readonly':''}>`;
      return `<label>${escapeHtml(tr(labels[key]))}${control}</label>`;
    }).join('');
    $('#catalogEditor').showModal();$('#catalogFields [name=product_name]').focus();
  }
  $('#catalogForm').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    const values=Object.fromEntries(new FormData(event.target));
    for(const key of numeric)values[key]=Number(values[key]);
    const stock=values.stock;delete values.stock;
    const account=activeAccountId,version=generation;busy=true;buttons();
    try{
      if(editing)await request('/api/catalog/'+encodeURIComponent(editing.id),jsonOptions('PUT',{fields:values,stock,revision:editing.revision}));
      else await importProducts([{fields:values,stock}]);
      if(!valid(account,version))return;
      $('#catalogEditor').close();clearSelection();feedback(tr('Product saved. Run a new analysis after changing pricing inputs.'));await load();
    }catch(error){if(valid(account,version))$('#catalogEditorError').textContent=error.message}
    finally{if(valid(account,version)){busy=false;buttons()}}
  });
  async function remove(product){
    if(!confirm(tr('Delete this product and its change history? Its monitor will be paused. Saved analyses remain in History.')))return;
    const account=activeAccountId,version=generation;busy=true;buttons();
    try{
      await request(`/api/catalog/${encodeURIComponent(product.id)}?revision=${product.revision}`,{method:'DELETE'});
      if(!valid(account,version))return;
      clearSelection();feedback(tr('Product deleted.'));await load();syncAccountData(true);
    }catch(error){if(valid(account,version))feedback(error.message)}finally{if(valid(account,version)){busy=false;buttons()}}
  }
  async function bulk(action){
    if(busy||!selection.size)return;
    const account=activeAccountId,version=generation;busy=true;buttons();feedback(tr('Saving selection…'));
    if(action==='analyze')pending=pending||{client_id:crypto.randomUUID(),products:[...selection.values()]};
    try{
      const data=await request('/api/catalog/'+action,jsonOptions('POST',action==='analyze'?pending:{products:[...selection.values()]}));
      if(!valid(account,version))return;
      clearSelection();
      if(action==='analyze'){feedback('');window.MarketBatches.open(data.id)}
      else{feedback(tr('Monitoring enabled for the selection. Sentinel must be running to collect data.'));await load();syncAccountData(true)}
    }catch(error){if(valid(account,version))feedback(error.message)}finally{if(valid(account,version)){busy=false;buttons()}}
  }
  async function loadRevisions(){
    const account=activeAccountId,version=generation,id=revisionProduct?.id,page=revisionOffset;
    if(!id)return;
    $('#catalogRevisionFeedback').textContent='';
    try{
      const data=await request(`/api/catalog/${encodeURIComponent(id)}/revisions?offset=${page}`);
      if(!valid(account,version)||revisionProduct?.id!==id||revisionOffset!==page)return;
      $('#catalogRevisionList').innerHTML=data.items.map(item=>`<details class="catalog-revision"><summary>${escapeHtml(tr('Revision'))} ${item.revision} · ${escapeHtml(new Date(item.created_at).toLocaleString(appLocale()))} · ${fmtMoney(item.fields.purchase_cost,item.fields.purchase_currency)}</summary><dl>${Object.entries({...item.fields,stock:item.stock}).map(([key,value])=>`<div><dt>${escapeHtml(tr(labels[key]||key))}</dt><dd>${escapeHtml(String(value??'—'))}</dd></div>`).join('')}</dl></details>`).join('');
      $('#catalogRevisionPrevious').disabled=page===0;$('#catalogRevisionNext').disabled=page+20>=data.total;
    }catch(error){if(valid(account,version))$('#catalogRevisionFeedback').textContent=error.message}
  }
  $('#catalogNew').addEventListener('click',()=>editor());
  $('#catalogEditorClose').addEventListener('click',()=>$('#catalogEditor').close());
  $('#catalogRevisionsClose').addEventListener('click',()=>{$('#catalogRevisions').close();revisionProduct=null});
  $('#catalogRevisionPrevious').addEventListener('click',()=>{revisionOffset=Math.max(0,revisionOffset-20);loadRevisions()});
  $('#catalogRevisionNext').addEventListener('click',()=>{revisionOffset+=20;loadRevisions()});
  $('#catalogRefresh').addEventListener('click',()=>{clearSelection();feedback('');load()});
  $('#catalogSelectAll').addEventListener('change',event=>{
    clearSelection();if(event.target.checked)for(const p of products)selection.set(p.id,{id:p.id,revision:p.revision});render();
  });
  for(const id of ['#catalogQuality','#catalogFreshness','#catalogSort'])$(id).addEventListener('change',()=>{offset=0;clearSelection();load()});
  $('#catalogSearch').addEventListener('input',()=>{if(searchTimer)clearTimeout(searchTimer);searchTimer=setTimeout(()=>{offset=0;clearSelection();load()},250)});
  $('#catalogPrevious').addEventListener('click',()=>{offset=Math.max(0,offset-50);clearSelection();load()});
  $('#catalogNext').addEventListener('click',()=>{offset+=50;clearSelection();load()});
  $('#catalogAnalyze').addEventListener('click',()=>bulk('analyze'));$('#catalogMonitor').addEventListener('click',()=>bulk('monitor'));
  function reset(){
    ++generation;++serial;if(searchTimer)clearTimeout(searchTimer);products=[];clearSelection();offset=total=0;busy=false;editing=revisionProduct=null;
    $('#catalogEditor').close();$('#catalogRevisions').close();$('#catalogFields').innerHTML='';$('#catalogRevisionList').innerHTML='';
    $('#catalogEditorError').textContent='';$('#catalogRevisionFeedback').textContent='';$('#catalogSearch').value='';
    for(const id of ['#catalogQuality','#catalogFreshness'])$(id).value='all';$('#catalogSort').value='sku';feedback('');render();
  }
  document.addEventListener('marketai:languagechange',()=>{render();if(active()&&$('#view-catalog').classList.contains('active'))load()});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&active()&&$('#view-catalog').classList.contains('active'))load()});
  window.MarketCatalog={load,reset,importProducts};
})();
