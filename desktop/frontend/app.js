const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const appLocale = () => window.MarketI18n?.locale?.() || 'en-US';
const tr = (value) => window.MarketI18n?.t?.(value) || value;
const fmtBRL = (n) => n == null || Number.isNaN(Number(n)) ? '—' : new Intl.NumberFormat(appLocale(),{style:'currency',currency:'BRL'}).format(Number(n));
const fmtMoney = (n,c='BRL') => { try { return new Intl.NumberFormat(appLocale(),{style:'currency',currency:c}).format(Number(n||0)); } catch { return `${Number(n||0).toFixed(2)} ${c}`; } };
const num = (v) => Number(v || 0);

const form = $('#analysisForm');
const loading = $('#loading');
const result = $('#result');
const imageInput = $('#imageInput');
const preview = $('#preview');
const uploadPrompt = $('#uploadPrompt');
let currentPreviewURL = '';
let currentAnalysis = null;
let currentFormSnapshot = null;
let activeAccountId = 'guest';
let accountSync = null;
let accountEpoch = 0;

function accountStorageKey(base){
  return `${base}:${activeAccountId || 'guest'}`;
}
function readAccountItems(base){
  try{return JSON.parse(localStorage.getItem(accountStorageKey(base))||'[]')}catch{return []}
}
function writeAccountItems(base,items){
  localStorage.setItem(accountStorageKey(base),JSON.stringify(items));
}

const countryCurrency = {BR:'BRL',US:'USD',CN:'CNY',FR:'EUR',DE:'EUR',GB:'GBP',JP:'JPY',KR:'KRW',MX:'MXN',AR:'ARS',CA:'CAD'};
const originCountry = form.elements.origin_country;
const purchaseCurrency = form.elements.purchase_currency;
originCountry.addEventListener('change', () => {
  const currency = countryCurrency[originCountry.value];
  if(currency && [...purchaseCurrency.options].some(o => o.value === currency)) purchaseCurrency.value = currency;
});

async function health(){
  try{
    const r = await fetch('/api/health'); const d = await r.json();
    $('#apiStatus').textContent = `${tr('API online')} · v${d.version}`;
    $('.status-dot').classList.add('live');
  }catch{ $('#apiStatus').textContent = tr('API offline'); }
}
health();

imageInput.addEventListener('change', () => {
  const file = imageInput.files?.[0]; if(!file) return;
  if(currentPreviewURL) URL.revokeObjectURL(currentPreviewURL);
  currentPreviewURL = URL.createObjectURL(file); preview.src = currentPreviewURL; preview.hidden = false; uploadPrompt.hidden = true;
});

function switchView(name){
  $$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===name));
  $$('.view').forEach(x=>x.classList.remove('active'));
  $(`#view-${name}`).classList.add('active');
  if(name==='history'){renderHistory();syncAccountData();}
  if(name==='watchlist'){renderWatchlist();syncAccountData();}
  if(name==='batches') window.MarketBatches?.load();
  if(name==='catalog') window.MarketCatalog?.load();
  if(name==='integrations') loadIntegrations();
  if(name==='settings') loadSettings();
}
$$('.nav-item').forEach(btn => btn.addEventListener('click', () => { switchView(btn.dataset.view); if(btn.dataset.view==='intelligence') loadIntelligence(); }));

const loadingSteps = [
  'Identifying product, variant and attributes.',
  'Querying only available real sources.',
  'Rejecting kits, testers, decants and incompatible variants.',
  'Validating volume, capacity, power and outliers.',
  'Calculating price only if the sample is reliable.'
];

function snapshotForm(){
  const out={}; new FormData(form).forEach((v,k)=>{ if(!(v instanceof File)) out[k]=v; }); return out;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault(); const requestAccount=activeAccountId; result.hidden = true; form.style.display = 'none'; loading.hidden = false; currentFormSnapshot=snapshotForm();
  let i=0; const timer=setInterval(()=>{$('#loadingText').textContent=tr(loadingSteps[(++i)%loadingSteps.length])},1100);
  try{
    const data=new FormData(form); const r=await fetch('/api/analyze',{method:'POST',body:data});
    if(!r.ok){let d={};try{d=await r.json()}catch{};const code=d.detail||'';if(r.status===401){setAuthScreen(false);throw new Error(tr('Sign in to your MarketAI account to analyze products.'))}if(r.status===403&&code==='device_not_authorized'){switchView('account');throw new Error(tr('This computer is not linked to your account yet. Sign out and sign in again to reactivate it.'))}if(r.status===429)throw new Error(tr('The server is temporarily rate-limiting requests. Try again in a moment.'));throw new Error(tr(d.message||d.detail||'Could not complete the analysis.'))}
    const analysis=await r.json(); if(requestAccount!==activeAccountId)return; currentAnalysis=analysis; renderAnalysis(analysis); saveHistory(analysis); setWorkflowStep('compare'); result.hidden=false; result.scrollIntoView({behavior:'smooth',block:'start'});loadCloudStatus();
  }catch(err){ alert(tr('I could not complete the analysis.')+'\n\n'+tr(err.message)); form.style.display='grid'; }
  finally{ clearInterval(timer); loading.hidden=true; }
});

$('#newAnalysis').addEventListener('click',()=>{result.hidden=true;form.style.display='grid';setWorkflowStep('analyze');window.scrollTo({top:0,behavior:'smooth'})});

function featureSummary(f={}){
  const parts=[];
  if(f.concentration) parts.push(String(f.concentration).toUpperCase());
  if(f.volume_ml!=null) parts.push(`${Number(f.volume_ml).toLocaleString(appLocale(),{maximumFractionDigits:1})} ml`);
  if(f.capacity_gb!=null) parts.push(`${Number(f.capacity_gb)} GB`);
  if(f.power_w!=null) parts.push(`${Number(f.power_w)} W`);
  if(f.kit) parts.push('kit'); if(f.tester) parts.push('tester'); if(f.decant) parts.push('decant');
  if(f.refill) parts.push('refill'); if(f.sample) parts.push('sample');
  return parts.join(' · ') || tr('not identified in title');
}

function qualityClass(state){
  if(state==='reliable') return 'good';
  if(state==='ambiguous' || state==='insufficient') return 'warn';
  return 'bad';
}

function renderQuality(d){
  const q=d.market.quality;
  $('#qualityTitle').textContent=q.label;
  $('#qualityMessage').textContent=q.message;
  const badge=$('#qualityBadge'); badge.textContent=tr(q.state==='reliable'?'APPROVED FOR PRICING':q.state==='ambiguous'?'AMBIGUOUS VARIANT':q.state==='insufficient'?'SMALL SAMPLE':'NO RELIABLE PRICE');
  badge.className=`quality-badge ${qualityClass(q.state)}`;
  $('#dataQualityCard').className=`card data-quality-card ${qualityClass(q.state)}`;
  $('#qualityCounts').textContent=tr(`${d.market.raw_count} encontrados · ${d.market.matched_count} compatíveis · ${d.market.pricing_count} usados no preço`);
  $('#qualityBlockers').innerHTML=(q.blockers||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join('');
  renderEvidence(d);
  $('#sourceStatus').innerHTML=(d.market.sources||[]).length
    ? d.market.sources.map(x=>{
        const cls=x.status==='ok'?'source-ok':(x.status==='not_configured'?'source-off':'source-warn');
        const status=x.status==='ok'?`${x.returned||0} ${tr('result(s)')}`:sourceStatusLabel(x.status);
        const collected=x.checked_at?`<small>${escapeHtml(tr('Collected at'))}: ${escapeHtml(new Date(x.checked_at).toLocaleString(appLocale()))}</small>`:'';
        const err=x.error?`<small>${escapeHtml(x.error)}</small>`:'';
        return `<span class="${cls}"><b>${escapeHtml(x.source)}</b>: ${escapeHtml(status)}${x.latency_ms?` · ${x.latency_ms} ms`:''}${err}${collected}</span>`;
      }).join('')
    : `<span>${escapeHtml(tr('No market source available for this country.'))}</span>`;
}

function sourceStatusLabel(status){
  return tr(({not_configured:'not configured',auth_required:'authentication required',rate_limited:'request limit',network_error:'network error',upstream_error:'source unavailable',http_error:'HTTP error',configured:'configured',fallback:'fallback'})[status]||status||'unavailable');
}

function renderAnalysis(d){
  const p=d.product, pr=d.pricing, rec=pr.strategies.recommended, reliable=d.market.reliable;
  $('#productTitle').textContent=p.product_name||d.request.typed_name;
  $('#productMeta').textContent=[p.brand,p.model,p.variant_summary||p.variant,p.category].filter(x=>x && String(x).toLowerCase()!=='a confirmar').join(' · ') || tr('Basic identification');
  $('#productCodes').textContent=[d.request.gtin?`GTIN: ${d.request.gtin}`:'',d.request.ncm?`NCM: ${d.request.ncm}`:'',d.request.supplier_name?`${tr('Supplier')}: ${d.request.supplier_name}`:''].filter(Boolean).join(' · ')||tr('No additional codes provided');
  $('#confidenceValue').textContent=`${p.confidence??0}%`; $('#confidenceBar').style.width=`${Math.max(0,Math.min(100,p.confidence||0))}%`;
  $('#resultThumb').innerHTML=currentPreviewURL?`<img src="${currentPreviewURL}" alt="${escapeAttr(tr('product'))}">`:'AI';

  renderQuality(d);
  renderNextAction(d);

  $('#scoreValue').textContent=reliable ? pr.opportunity.score : '—';
  $('#scoreLabel').textContent=reliable ? tr(pr.opportunity.label) : tr('Score blocked until reliable market data exists');
  $('#scoreLabel').style.color=reliable?(pr.opportunity.signal==='red'?'var(--red)':pr.opportunity.signal==='yellow'?'var(--yellow)':'var(--green)'):'var(--muted)';

  $('#marketMedian').textContent=reliable?fmtBRL(pr.market.median):tr('No median');
  $('#marketMedianCaption').textContent=reliable?tr(`${pr.market.count} anúncio(s) usados no cálculo`):tr('no fictitious price will be used');
  $('#recommendedPrice').textContent=rec?fmtBRL(rec.price):tr('BLOCKED');
  $('#recommendedCaption').textContent=rec?tr('balance between margin and compatible market'):`${tr('minimum based on your costs')}: ${fmtBRL(pr.costs.minimum_for_target_margin)}`;
  $('#recommendedProfit').textContent=rec?fmtBRL(rec.net_profit):'—';
  $('#recommendedMargin').textContent=rec?`${tr('Margin')} ${rec.net_margin_percent}% · ROI ${rec.roi_percent}%`:tr('no estimated market profit');
  $('#unitCost').textContent=fmtBRL(pr.costs.unit_cost); $('#breakEven').textContent=`${tr('Break-even')}: ${fmtBRL(pr.costs.break_even)}`;

  $('#verdictTitle').textContent=d.advice.verdict; $('#verdictSummary').textContent=d.advice.summary;
  $('#verdictReasons').innerHTML=(d.advice.reasons.length?d.advice.reasons:[tr('No additional positive point identified.')]).map(x=>`<li>${escapeHtml(x)}</li>`).join('');
  $('#verdictRisks').innerHTML=(d.advice.risks.length?d.advice.risks:[tr('No relevant alerts for the assumptions provided.')]).map(x=>`<li>${escapeHtml(x)}</li>`).join('');

  const strategyNames={fast_sale:['Quick sale','aggressive entry'],recommended:['Recommended','best balance'],margin:['More margin','higher profit'],premium:['Premium','high positioning']};
  if(rec){
    $('#strategies').innerHTML=Object.entries(pr.strategies).map(([key,x])=>{if(!x)return ''; const [name,desc]=strategyNames[key];return `<div class="strategy ${key==='recommended'?'recommended':''}"><span>${escapeHtml(tr(name))}</span><strong>${fmtBRL(x.price)}</strong><small>${escapeHtml(tr(desc))}</small><small>${escapeHtml(tr('Profit'))}: ${fmtBRL(x.net_profit)} · ${x.net_margin_percent}% · ROI ${x.roi_percent}%</small>${key==='recommended'?`<em>${escapeHtml(tr('RECOMMENDED BY AI'))}</em>`:''}</div>`}).join('');
  }else{
    const floor=pr.cost_floor;
    $('#strategies').innerHTML=`<div class="strategy cost-only"><span>${escapeHtml(tr('Minimum based on your costs'))}</span><strong>${fmtBRL(floor.price)}</strong><small>${escapeHtml(tr('Minimum price to reach your desired margin.'))}</small><small>${escapeHtml(tr('Calculated profit'))}: ${fmtBRL(floor.net_profit)} · ${floor.net_margin_percent}%</small><em>${escapeHtml(tr('NOT A MARKET PRICE'))}</em></div><div class="empty compact strategy-empty">${escapeHtml(tr('The four strategies will be unlocked when there is enough real data and an unambiguous variant.'))}</div>`;
  }

  $('#fxCurrency').textContent=d.request.purchase_currency; $('#fxRate').textContent=Number(d.fx.rate).toLocaleString(appLocale(),{minimumFractionDigits:2,maximumFractionDigits:6}); $('#fxSource').textContent=d.fx.source; $('#fxDate').textContent=`${tr('Reference')}: ${d.fx.date||'—'}`; $('#fxLive').textContent=d.fx.live?tr('live source'):tr('fallback rate');

  setupSimulator(d);
  renderComparison(d.comparison);
  renderSourceCards(d.market.by_source, reliable);
  renderCostBreakdown(pr.costs);
  renderMarketTables(d);
}

function setupSimulator(d){
  const s=d.pricing.simulation, costs=d.pricing.costs, med=d.pricing.market.median, slider=$('#priceSlider'), marketBased=d.market.reliable;
  slider.min=s.min_price; slider.max=Math.max(s.max_price,s.min_price+1); slider.value=s.initial_price; slider.step=Math.max(.01,(slider.max-slider.min)/500);
  $('#simMin').textContent=fmtBRL(slider.min); $('#simMax').textContent=fmtBRL(slider.max);
  const update=()=>{
    const price=num(slider.value), rate=costs.variable_rate_percent/100, unit=costs.unit_cost, profit=price*(1-rate)-unit, margin=price?profit/price*100:0, roi=unit?profit/unit*100:0, delta=med?((price-med)/med*100):0;
    $('#simPrice').textContent=fmtBRL(price); $('#simProfit').textContent=fmtBRL(profit); $('#simMargin').textContent=`${margin.toFixed(2)}%`; $('#simRoi').textContent=`${roi.toFixed(2)}%`;
    if(!marketBased){ $('#simCompetitive').textContent='Sem referência'; $('#simPosition').textContent='simulação baseada só nos custos'; return; }
    let comp='Alta'; if(delta>15) comp='Baixa'; else if(delta>7) comp='Média'; else if(delta<-12) comp='Muito alta';
    $('#simCompetitive').textContent=comp; $('#simPosition').textContent=`${Math.abs(delta).toFixed(1)}% ${delta>=0?'acima':'abaixo'} da mediana`;
  };
  slider.oninput=update; update();
}

function renderComparison(c){
  const card=$('#comparisonCard'); if(!c){card.hidden=true;return;} card.hidden=false;
  $('#nationalCost').textContent=fmtBRL(c.national_reference_cost); $('#importCost').textContent=fmtBRL(c.landed_import_cost); $('#cheaperOption').textContent=c.cheaper_option==='importado'?'Importar':'Comprar nacional'; $('#comparisonDiff').textContent=`diferença de ${fmtBRL(Math.abs(c.difference))} (${c.difference_percent}%)`;
}

function renderSourceCards(items,reliable){
  $('#marketSourceCards').innerHTML=items.length?items.map(x=>`<div class="source-card"><span>${escapeHtml(x.source)}</span><strong>${fmtBRL(x.median)}</strong><small>${x.count} compatível(is) · ${fmtBRL(x.min)} a ${fmtBRL(x.max)}</small>${!reliable?'<em class="not-priced">não usado como recomendação</em>':''}</div>`).join(''):'<div class="empty compact">Nenhuma fonte retornou anúncios compatíveis.</div>';
}

function renderCostBreakdown(c){
  const items=[['Compra',c.purchase_cost_brl],['Frete',c.freight_brl],['Importação',c.import_cost_brl],['Embalagem',c.packaging_brl],['Outros',c.other_costs_brl]].filter(x=>num(x[1])>0);
  const total=Math.max(c.unit_cost,1); $('#costBreakdown').innerHTML=items.length?items.map(([name,val])=>`<div class="cost-row"><div><span>${name}</span><strong>${fmtBRL(val)}</strong></div><div class="cost-bar"><i style="width:${Math.max(2,val/total*100)}%"></i></div></div>`).join(''):'<div class="empty compact">Informe custos para visualizar a composição.</div>';
}

function renderMarketTables(d){
  const q=d.market.quality;
  $('#marketMode').textContent=`Busca: ${d.market.query || d.request.typed_name} · ${q.label}`;
  $('#marketCheckedAt').textContent=d.market.checked_at?`Coleta: ${new Date(d.market.checked_at).toLocaleString(appLocale())} · ${d.market.live_source_count||0} fonte(s) respondendo · ${d.market.merchant_count||0} loja(s)/vendedor(es)`:'—';
  $('#tableStats').textContent=`${d.market.matched_count} compatíveis · ${d.market.pricing_count} usados no cálculo`;
  $('#marketRows').innerHTML=d.market.listings.length?d.market.listings.map(x=>`<tr>
    <td><span class="match-pill ${x.match_score>=85?'high':x.match_score>=70?'mid':'low'}">${x.match_score??0}%</span>${x.used_for_pricing?'<small class="used-tag">usado</small>':''}</td>
    <td>${escapeHtml(x.source)}</td>
    <td>${escapeHtml(listingMerchant(x))}</td>
    <td>${x.url?`<a href="${safeUrl(x.url)}" target="_blank" rel="noopener">${escapeHtml(x.title)}</a>`:escapeHtml(x.title)}</td>
    <td>${escapeHtml(featureSummary(x.features))}</td>
    <td>${fmtBRL(x.price_brl)}<small class="original-price">${fmtMoney(x.price,x.currency)}</small></td>
  </tr>`).join(''):'<tr><td colspan="6" class="table-empty">Nenhum anúncio compatível para exibir.</td></tr>';

  const discarded=d.market.discarded||[], card=$('#discardedCard');
  card.hidden=!discarded.length;
  $('#discardedStats').textContent=discarded.length?`${discarded.length} descartado(s)`:'';
  $('#discardedRows').innerHTML=discarded.map(x=>`<tr>
    <td><span class="match-pill low">${x.match_score??0}%</span></td>
    <td>${escapeHtml(x.source)}</td>
    <td>${escapeHtml(listingMerchant(x))}</td>
    <td>${x.url?`<a href="${safeUrl(x.url)}" target="_blank" rel="noopener">${escapeHtml(x.title)}</a>`:escapeHtml(x.title)}</td>
    <td>${fmtBRL(x.price_brl)}</td>
    <td class="reject-reason">${escapeHtml(x.rejection_reason||'incompatível')}</td>
  </tr>`).join('');
}

function listingMerchant(x){
  const m=x?.metadata||{};
  return m.merchant||m.official_store_name||m.seller_nickname||m.seller_username||(m.seller_id?`Seller ${m.seller_id}`:'—');
}

function saveHistory(d){
  const rec=d.pricing.strategies.recommended;
  const items=readAccountItems('marketai-history');
  items.unshift({id:d.history_id||null,date:new Date().toISOString(),name:d.product.product_name||d.request.typed_name,recommended:rec?.price??null,score:d.pricing.opportunity.score??null,marketMedian:d.market.reliable?d.pricing.market.median:null,mode:d.market.quality.state});
  writeAccountItems('marketai-history',items.slice(0,80));
  syncAccountData(true);
}

function renderHistory(){
  const items=readAccountItems('marketai-history');
  $('#historyList').innerHTML=items.length?items.map(x=>`<div class="history-item"><div><strong>${escapeHtml(x.name)}</strong><small>${new Date(x.date).toLocaleString(appLocale())} · ${escapeHtml(historyModeLabel(x.mode))}</small></div><div><small>MarketAI</small><div>${x.score==null?'—':x.score+'/100'}</div></div><div class="history-price">${x.recommended==null?'sem recomendação':fmtBRL(x.recommended)}</div>${x.imported?`<small>${escapeHtml(tr('Imported summary'))}</small>`:x.id?`<button class="ghost reopen-analysis" data-id="${escapeAttr(x.id)}">${escapeHtml(tr('Open analysis'))}</button>`:''}</div>`).join(''):'<div class="empty">Nenhuma análise salva ainda.</div>';
  renderHistoryChart(items);
  $$('.reopen-analysis').forEach(button=>button.addEventListener('click',()=>openSavedAnalysis(button.dataset.id)));

}
function historyModeLabel(mode){return ({reliable:'mercado confiável',ambiguous:'variante ambígua',insufficient:'amostra insuficiente',no_match:'sem match',unavailable:'sem fonte'})[mode]||mode||'—'}

function renderHistoryChart(items){
  const valid=items.filter(x=>x.recommended!=null && x.marketMedian!=null);
  const el=$('#historyChart'); if(!valid.length){el.innerHTML='<div class="empty">O gráfico aparece quando houver análises com mercado confiável.</div>';return;}
  const latest=valid[0].name, data=valid.filter(x=>x.name===latest).slice(0,12).reverse();
  if(data.length<2){el.innerHTML=`<div class="empty">Mais uma análise confiável de <strong>${escapeHtml(latest)}</strong> criará a linha histórica.</div>`;return;}
  const vals=data.flatMap(x=>[num(x.recommended),num(x.marketMedian)]), min=Math.min(...vals)*.95, max=Math.max(...vals)*1.05, w=720,h=260,pad=34;
  const pt=(v,i)=>{const x=pad+(w-pad*2)*(i/(data.length-1));const y=h-pad-(h-pad*2)*((v-min)/(max-min||1));return [x,y]};
  const line=(key)=>data.map((x,i)=>pt(num(x[key]),i).join(',')).join(' ');
  el.innerHTML=`<div class="chart-title">${escapeHtml(latest)}</div><svg viewBox="0 0 ${w} ${h}" role="img"><line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" class="axis"/><polyline points="${line('marketMedian')}" class="line median-line"/><polyline points="${line('recommended')}" class="line rec-line"/>${data.map((x,i)=>{const [cx,cy]=pt(num(x.recommended),i);return `<circle cx="${cx}" cy="${cy}" r="4" class="dot"><title>${fmtBRL(x.recommended)} — ${new Date(x.date).toLocaleDateString(appLocale())}</title></circle>`}).join('')}</svg><div class="legend"><span><i class="rec-key"></i>Preço recomendado</span><span><i class="med-key"></i>Mediana</span></div>`;
}
$('#clearHistory').addEventListener('click',async()=>{
  if(!confirm(tr('Clear history on all devices?')))return;
  const account=activeAccountId;
  try{await intelJson('/api/history',{method:'DELETE'});if(account!==activeAccountId)return;writeAccountItems('marketai-history',[]);renderHistory();await syncAccountData(true);}catch(e){setSyncStatus(tr('Sync failed. Local data was preserved.')+' '+e.message)}
});

function renderWatchlist(){
  const items=readAccountItems('marketai-watch');
  $('#watchList').innerHTML=items.length?items.map((x,i)=>`<div class="history-item watch-item"><div><strong>${escapeHtml(x.name)}</strong><small>${escapeHtml(x.variant||'')} · ${escapeHtml(x.country||'')} · ${x.date?new Date(x.date).toLocaleString(appLocale()):escapeHtml(tr('No snapshots yet'))}</small></div><div><small>Score</small><div>${x.score==null?'—':x.score+'/100'}</div></div><div class="history-price">${intelMoney(x.recommended)}</div><div class="action-row"><button class="ghost reanalyze" data-i="${i}">${escapeHtml(tr('Reanalyze'))}</button>${x.id?`<button class="ghost check-watch" data-id="${escapeAttr(x.id)}">${escapeHtml(tr('Check now'))}</button><button class="ghost alert-rules-watch" data-id="${escapeAttr(x.id)}">${escapeHtml(tr('Alert rules'))}</button><button class="ghost forecast-watch" data-id="${escapeAttr(x.id)}">Forecast</button><button class="ghost remove-watch" data-id="${escapeAttr(x.id)}">${escapeHtml(tr('Remove'))}</button>`:''}</div></div>`).join(''):`<div class="empty">${escapeHtml(tr('No monitored products. Analyze a product and select Monitor.'))}</div>`;
  $$('.reanalyze').forEach(btn=>btn.addEventListener('click',()=>loadWatch(items[num(btn.dataset.i)])));
  $$('.alert-rules-watch').forEach(btn=>btn.addEventListener('click',()=>window.MarketAlerts.open(btn.dataset.id)));
  $$('.check-watch').forEach(btn=>btn.addEventListener('click',async()=>{
    btn.disabled=true; const account=activeAccountId;
    try{await intelJson(`/api/intelligence/watches/${encodeURIComponent(btn.dataset.id)}/check`,{method:'POST'});if(account!==activeAccountId)return;await syncAccountData(true);}catch(e){setSyncStatus(e.message)}finally{btn.disabled=false}
  }));
  $$('.remove-watch').forEach(btn=>btn.addEventListener('click',async()=>{
    if(!confirm(tr('Stop monitoring this product on all devices?')))return;
    try{await intelJson(`/api/intelligence/watches/${encodeURIComponent(btn.dataset.id)}`,{method:'DELETE'});await syncAccountData(true);}catch(e){setSyncStatus(e.message)}
  }));
  $$('.forecast-watch').forEach(btn=>btn.addEventListener('click',async()=>{switchView('intelligence');await loadIntelligence();$('#forecastTarget').value=btn.dataset.id;showForecast(btn.dataset.id)}));
}
function loadWatch(item){ Object.entries(item.form||{}).forEach(([k,v])=>{const el=form.elements[k];if(el)el.value=v;}); switchView('analyze'); result.hidden=true; form.style.display='grid';setWorkflowStep('analyze'); window.scrollTo({top:0,behavior:'smooth'}); }
$('#clearWatchlist').addEventListener('click',async()=>{
  if(!confirm(tr('Stop monitoring all products on all devices?')))return;
  const account=activeAccountId;
  try{await intelJson('/api/intelligence/watches',{method:'DELETE'});if(account!==activeAccountId)return;writeAccountItems('marketai-watch',[]);renderWatchlist();await syncAccountData(true);}catch(e){setSyncStatus(tr('Sync failed. Local data was preserved.')+' '+e.message)}
});
$('#refreshHistory').addEventListener('click',()=>syncAccountData(true));
$('#refreshWatchlist').addEventListener('click',()=>syncAccountData(true));

$('#printReport').addEventListener('click',()=>window.print());
$('#exportCsv').addEventListener('click',()=>{
  if(!currentAnalysis)return; const d=currentAnalysis, rec=d.pricing.strategies.recommended;
  const rows=[['MarketAI v1.4.0 Community'],['Produto',d.product.product_name||d.request.typed_name],['Variante',d.request.variant_text||d.product.variant_summary||''],['Qualidade',d.market.quality.label],['Score',d.pricing.opportunity.score??'bloqueado'],['Veredito',d.advice.verdict],['Custo real',d.pricing.costs.unit_cost],['Piso pela margem',d.pricing.costs.minimum_for_target_margin],['Preço recomendado',rec?.price??'indisponível'],['Lucro líquido',rec?.net_profit??'indisponível'],['Margem %',rec?.net_margin_percent??'indisponível'],[],['STATUS','Match','Fonte','Anúncio','Moeda','Preço original','Preço BRL','Motivo'],...d.market.listings.map(x=>['COMPATÍVEL',x.match_score,x.source,x.title,x.currency,x.price,x.price_brl,x.used_for_pricing?'USADO NO CÁLCULO':'']),...d.market.discarded.map(x=>['DESCARTADO',x.match_score,x.source,x.title,x.currency,x.price,x.price_brl,x.rejection_reason])];
  const csv='\ufeff'+rows.map(r=>r.map(v=>`"${String(v??'').replaceAll('"','""')}"`).join(';')).join('\n'); const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`marketai-${slugify(d.request.typed_name)}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
});

function slugify(s='produto'){return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'')||'produto'}
function escapeHtml(s=''){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function escapeAttr(s=''){return escapeHtml(s).replace(/`/g,'&#96;')}
function safeUrl(url=''){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)?u.href:'#'}catch{return '#'}}




const credentialFields={
  OPENAI_API_KEY:'#settingsOpenAI',
  MERCADOLIVRE_ACCESS_TOKEN:'#settingsML',
  EBAY_CLIENT_ID:'#settingsEbayId',
  EBAY_CLIENT_SECRET:'#settingsEbaySecret',
  SERPAPI_KEY:'#settingsSerp'
};
const credentialStateIds={
  OPENAI_API_KEY:'#cred-openai',MERCADOLIVRE_ACCESS_TOKEN:'#cred-ml',EBAY_CLIENT_ID:'#cred-ebay-id',EBAY_CLIENT_SECRET:'#cred-ebay-secret',SERPAPI_KEY:'#cred-serp'
};
let cachedSettings=null;

function setCredentialStates(credentials={}){
  Object.entries(credentialStateIds).forEach(([key,sel])=>{
    const el=$(sel); if(!el)return;
    const on=!!credentials[key]; el.textContent=on?'SALVA':'NÃO CONFIGURADA'; el.className=`cred-state ${on?'on':'off'}`;
  });
}
function applyPreferencesToForm(p={}){
  const pairs={origin_country:p.default_origin_country,destination_country:p.default_destination_country,purchase_currency:p.default_purchase_currency,marketplace_fee_percent:p.default_marketplace_fee_percent,taxes_percent:p.default_taxes_percent,ads_percent:p.default_ads_percent,desired_margin_percent:p.default_margin_percent};
  Object.entries(pairs).forEach(([name,value])=>{const el=form.elements[name];if(el && value!==undefined && value!==null) el.value=value;});
}
async function loadSettings(applyForm=false){
  try{
    const r=await fetch('/api/settings'); const d=await r.json(); cachedSettings=d;
    setCredentialStates(d.credentials||{});
    const p=d.preferences||{};
    if($('#prefOrigin')) $('#prefOrigin').value=p.default_origin_country||'CN';
    if($('#prefDestination')) $('#prefDestination').value=p.default_destination_country||'BR';
    if($('#prefCurrency')) $('#prefCurrency').value=p.default_purchase_currency||'BRL';
    if($('#prefFee')) $('#prefFee').value=p.default_marketplace_fee_percent??16;
    if($('#prefTax')) $('#prefTax').value=p.default_taxes_percent??6;
    if($('#prefAds')) $('#prefAds').value=p.default_ads_percent??3;
    if($('#prefMargin')) $('#prefMargin').value=p.default_margin_percent??20;
    if(applyForm) applyPreferencesToForm(p);
  }catch(e){console.warn('settings',e)}
}

$('#saveCredentials')?.addEventListener('click',async()=>{
  const btn=$('#saveCredentials'); btn.disabled=true;
  const values={}; Object.entries(credentialFields).forEach(([key,sel])=>{const value=$(sel)?.value?.trim();if(value)values[key]=value});
  try{
    const r=await fetch('/api/settings/integrations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values})});
    if(!r.ok) throw new Error(await r.text()); const d=await r.json();
    Object.values(credentialFields).forEach(sel=>{if($(sel))$(sel).value=''}); setCredentialStates(d.credentials||{}); await health();
    alert('Credenciais salvas com segurança neste usuário do Windows.');
  }catch(e){alert('Não foi possível salvar as credenciais.\n\n'+e.message)}finally{btn.disabled=false}
});
$('#clearCredentials')?.addEventListener('click',async()=>{
  if(!confirm('Remover todas as credenciais salvas do MarketAI neste computador?'))return;
  const clear=Object.keys(credentialFields);
  const r=await fetch('/api/settings/integrations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clear})});
  const d=await r.json(); setCredentialStates(d.credentials||{}); await health();
});
$('#savePreferences')?.addEventListener('click',async()=>{
  const payload={default_origin_country:$('#prefOrigin').value,default_destination_country:$('#prefDestination').value,default_purchase_currency:$('#prefCurrency').value,default_marketplace_fee_percent:num($('#prefFee').value),default_taxes_percent:num($('#prefTax').value),default_ads_percent:num($('#prefAds').value),default_margin_percent:num($('#prefMargin').value)};
  const r=await fetch('/api/settings/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok){alert('Não foi possível salvar as preferências.');return} const d=await r.json(); applyPreferencesToForm(d.preferences||{}); alert('Preferências salvas.');
});

function downloadJson(filename,data){
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
$('#exportBackup')?.addEventListener('click',()=>downloadJson(`marketai-backup-${new Date().toISOString().slice(0,10)}.json`,{format:'MarketAIBackup',version:'1.4.0',account_id:activeAccountId,exported_at:new Date().toISOString(),history:readAccountItems('marketai-history'),watchlist:readAccountItems('marketai-watch')}));
$('#importBackupBtn')?.addEventListener('click',()=>$('#importBackupFile').click());
$('#importBackupFile')?.addEventListener('change',async e=>{
  const file=e.target.files?.[0];if(!file)return;
  const account=activeAccountId;
  try{
    const d=JSON.parse(await file.text());
    if(d.format!=='MarketAIBackup')throw new Error(tr('Unrecognized backup file.'));
    if(d.account_id && d.account_id!==account)throw new Error(tr('This backup belongs to another account.'));
    if(accountSync?.account===account)await accountSync.promise;
    if(account!==activeAccountId)return;
    if(Array.isArray(d.history)&&d.history.length){await intelJson('/api/history/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:importableHistory(d.history)})});}
    for(const item of Array.isArray(d.watchlist)?d.watchlist:[]){
      if(account!==activeAccountId)return;
      await intelJson('/api/intelligence/watches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item.form,product_name:item.name,autopilot_enabled:false})});
    }
    await syncAccountData(true);alert(tr('Backup merged into your account. History is imported as summaries.'));
  }catch(err){alert(tr('Could not import the backup.')+'\n\n'+err.message)}finally{e.target.value=''}
});
$('#exportDiagnostics')?.addEventListener('click',async()=>{try{const r=await fetch('/api/app/diagnostics');downloadJson(`marketai-diagnostico-${new Date().toISOString().replaceAll(':','-')}.json`,await r.json())}catch(e){alert('Não foi possível gerar o diagnóstico.')}});
$('#openDataFolder')?.addEventListener('click',async()=>{try{const r=await fetch('/api/app/open-data-folder',{method:'POST'});const d=await r.json();if(!d.ok)alert(`Pasta de dados: ${d.path||'—'}`)}catch(e){alert('Não foi possível abrir a pasta de dados.')}});

async function loadAppInfo(){
  try{const r=await fetch('/api/app/info');const d=await r.json();$('#appVersion').textContent=`MarketAI v${d.version}`;$('#aboutVersion').textContent=`v${d.version}`;}catch{}
}
async function handleFirstRun(){
  try{
    const r=await fetch('/api/setup/status'); const d=await r.json();
    if(d.preferences) applyPreferencesToForm(d.preferences);
    if(!d.first_run_completed){
      await fetch('/api/setup/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    }
  }catch{}
}
loadAppInfo(); loadSettings(true); handleFirstRun();

const integrationLabels={mercadolivre:'Mercado Livre',ebay:'eBay',google_shopping:'Google Shopping via SerpApi',bcb:'Banco Central — PTAX',vision:'Visão por IA'};
function integrationIcon(id){return ({mercadolivre:'ML',ebay:'eB',google_shopping:'GS',bcb:'BC',vision:'AI'})[id]||'API'}
function integrationDescription(id){return ({
  mercadolivre:'Anúncios ativos do Mercado Livre. Token recomendado para acesso consistente e catálogo.',
  ebay:'Browse API com OAuth Client Credentials e marketplace do país selecionado.',
  google_shopping:'Agrega ofertas reais de várias lojas usando pesquisa localizada do Google Shopping.',
  bcb:'PTAX oficial para conversão cambial para BRL.',
  vision:'Identifica marca, modelo, variante, volume/capacidade e outros atributos pela foto.'
})[id]||''}
async function loadIntegrations(){
  const grid=$('#integrationStatusGrid'); if(!grid) return;
  grid.innerHTML='<div class="empty">Carregando integrações…</div>';
  try{
    const r=await fetch('/api/integrations/status'); const d=await r.json();
    grid.innerHTML=(d.integrations||[]).map(x=>`<div class="card integration live-integration" data-source="${escapeHtml(x.id)}">
      <span class="integration-icon">${integrationIcon(x.id)}</span>
      <div class="integration-body"><div class="integration-title"><h3>${escapeHtml(x.name)}</h3><span class="integration-state ${x.configured?'on':'off'}">${x.configured?'CONFIGURADO':'PENDENTE'}</span></div>
      <p>${escapeHtml(integrationDescription(x.id))}</p><small>${escapeHtml(x.mode||'—')}${x.countries?.length?` · ${x.countries.join(', ')}`:''}</small>
      <div class="integration-test-result" id="test-${escapeHtml(x.id)}"></div>
      <button class="ghost integration-test" data-test-source="${escapeHtml(x.id)}">Testar conexão</button></div>
    </div>`).join('');
    $$('.integration-test').forEach(b=>b.addEventListener('click',()=>testIntegration(b.dataset.testSource,b)));
  }catch(e){grid.innerHTML=`<div class="empty">Não consegui carregar o status: ${escapeHtml(e.message)}</div>`}
}
async function testIntegration(source,button){
  const box=$(`#test-${source}`); if(!box) return;
  button.disabled=true; box.className='integration-test-result testing'; box.textContent='Testando…';
  try{
    const r=await fetch(`/api/integrations/test?source=${encodeURIComponent(source)}`); const d=await r.json();
    const ok=d.status==='ok'||d.status==='configured';
    box.className=`integration-test-result ${ok?'ok':'bad'}`;
    box.textContent=ok?`OK · ${d.returned||0} retorno(s)${d.latency_ms?` · ${d.latency_ms} ms`:''}`:`${sourceStatusLabel(d.status)}${d.error?` · ${d.error}`:''}`;
  }catch(e){box.className='integration-test-result bad';box.textContent=e.message}
  finally{button.disabled=false}
}
$('#refreshIntegrations')?.addEventListener('click',loadIntegrations);


// ===================== MARKETAI COMMUNITY ACCOUNT =====================
let cloudAccount=null;
let appModalOnClose=null;

function cloudError(d){
  const code=d?.detail||d?.message||'';
  const map={
    invalid_credentials:'E-mail ou senha incorretos.',
    email_already_registered:'Este e-mail já possui uma conta.',
    invalid_email_or_password:'Informe um e-mail válido e uma senha com pelo menos 8 caracteres.',
    terms_required:'É necessário aceitar os termos para criar a conta.',
    account_inactive:'Esta conta está desativada.',
    cloud_unavailable:'O MarketAI Cloud está indisponível no momento. Tente novamente em instantes.'
  };
  return map[code]||code||'Não foi possível concluir a operação.';
}

function setAuthScreen(logged){
  const gate=$('#authGate'), shell=$('#appShell');
  if(gate){
    gate.hidden=!!logged;
    gate.setAttribute('aria-hidden',logged?'true':'false');
  }
  if(shell){
    shell.hidden=!logged;
    shell.setAttribute('aria-hidden',logged?'false':'true');
  }
  document.body.classList.toggle('is-authenticated',!!logged);
  if(!logged){
    if($('#loginCard'))$('#loginCard').hidden=false;
    if($('#registerCard'))$('#registerCard').hidden=true;
  }
}

function applyAccountData(d={}){
  const u=d.user||{},e=d.entitlement||{};
  cloudAccount={authenticated:true,...d};
  const nextAccount=String(u.id||u.email||'account');
  if(activeAccountId!==nextAccount){resetAnalysis();accountSync=null;}
  activeAccountId=nextAccount;
  renderHistory();renderWatchlist();syncAccountData();
  if($('#accountName'))$('#accountName').textContent=u.full_name||'Conta MarketAI';
  if($('#accountEmail'))$('#accountEmail').textContent=u.email||'—';
  if($('#accountPlan'))$('#accountPlan').textContent='COMMUNITY';
  if($('#accountRemaining'))$('#accountRemaining').textContent='GRÁTIS';
  if($('#accountQuota'))$('#accountQuota').textContent='ILIMITADAS';
  if($('#accountStatus'))$('#accountStatus').textContent='ATIVO';
  setAuthScreen(true);
  document.dispatchEvent(new CustomEvent('marketai:accountready',{detail:{id:activeAccountId}}));
}

function setAuthFeedback(id,message='',kind='error'){
  const el=$(id); if(!el)return;
  el.textContent=message;
  el.className=`auth-feedback ${kind}`;
  el.hidden=!message;
}

function setAuthBusy(button,busy,label){
  if(!button)return;
  if(!button.dataset.defaultLabel)button.dataset.defaultLabel=button.querySelector('span')?.textContent||label;
  button.disabled=busy;
  const span=button.querySelector('span');
  if(span)span.textContent=busy?label:button.dataset.defaultLabel;
  button.classList.toggle('is-busy',busy);
}

function openAppModal({eyebrow='MARKETAI',title='Tudo certo.',message='',symbol='✓',button='CONTINUAR',onClose=null}={}){
  const modal=$('#appModal'); if(!modal)return;
  $('#appModalEyebrow').textContent=eyebrow;
  $('#appModalTitle').textContent=title;
  $('#appModalMessage').textContent=message;
  $('#appModalSymbol').textContent=symbol;
  $('#appModalAction span').textContent=button;
  appModalOnClose=onClose;
  modal.hidden=false;
  modal.setAttribute('aria-hidden','false');
  setTimeout(()=>$('#appModalAction')?.focus(),20);
}

function closeAppModal(){
  const modal=$('#appModal'); if(!modal)return;
  modal.hidden=true;
  modal.setAttribute('aria-hidden','true');
  const callback=appModalOnClose;
  appModalOnClose=null;
  if(typeof callback==='function')callback();
}

$('#appModalAction')?.addEventListener('click',closeAppModal);
$('[data-modal-close]')?.addEventListener('click',closeAppModal);
document.addEventListener('keydown',e=>{if(e.key==='Escape' && !$('#appModal')?.hidden)closeAppModal()});

async function loadCloudStatus(){
  const epoch=accountEpoch;
  try{
    const r=await fetch('/api/cloud/status');
    const d=await r.json();
    if(epoch!==accountEpoch)return false;
    if(!r.ok || !d.authenticated){
      cloudAccount={authenticated:false,...d};
      resetAnalysis();accountSync=null;activeAccountId='guest';
      renderHistory();renderWatchlist();setAuthScreen(false);
      return false;
    }
    applyAccountData(d);
    await loadDevices();
    return true;
  }catch(e){
    if(epoch!==accountEpoch)return false;
    resetAnalysis();accountSync=null;
    cloudAccount={authenticated:false,error:e.message};
    activeAccountId='guest';
    setAuthScreen(false);
    return false;
  }
}

async function doCloudAuth(path,payload){
  const epoch=++accountEpoch;
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(cloudError(d));
  if(epoch!==accountEpoch)throw new Error(tr('Authentication changed. Please try again.'));

  // Login/register already returns the authenticated account. Apply it immediately
  // instead of depending on a second request before hiding the login screen.
  applyAccountData(d);
  loadDevices();
  return d;
}

$('#cloudLogin')?.addEventListener('click',async()=>{
  const button=$('#cloudLogin');
  setAuthFeedback('#loginFeedback','');
  setAuthBusy(button,true,'ENTRANDO…');
  try{
    await doCloudAuth('/api/cloud/login',{
      email:$('#cloudEmail').value.trim(),
      password:$('#cloudPassword').value
    });
    switchView('analyze');
  }catch(e){
    setAuthScreen(false);
    setAuthFeedback('#loginFeedback',e.message,'error');
  }finally{
    setAuthBusy(button,false,'ENTRANDO…');
  }
});

$('#cloudRegister')?.addEventListener('click',async()=>{
  const button=$('#cloudRegister');
  setAuthFeedback('#registerFeedback','');
  setAuthBusy(button,true,'CRIANDO…');
  try{
    const data=await doCloudAuth('/api/cloud/register',{
      full_name:$('#regName').value.trim(),
      email:$('#regEmail').value.trim(),
      password:$('#regPassword').value
    });
    switchView('analyze');
    openAppModal({
      eyebrow:'CONTA CRIADA',
      title:'Bem-vindo ao MarketAI.',
      message:`Sua conta ${data.user?.email||''} foi criada com sucesso. Todos os recursos Community estão liberados gratuitamente.`,
      symbol:'✓',
      button:'ENTRAR NO MARKETAI',
      onClose:()=>switchView('analyze')
    });
  }catch(e){
    setAuthScreen(false);
    $('#loginCard').hidden=true;
    $('#registerCard').hidden=false;
    setAuthFeedback('#registerFeedback',e.message,'error');
  }finally{
    setAuthBusy(button,false,'CRIANDO…');
  }
});

$('#showRegister')?.addEventListener('click',()=>{
  setAuthFeedback('#loginFeedback','');
  $('#loginCard').hidden=true;
  $('#registerCard').hidden=false;
  $('#regName')?.focus();
});
$('#showLogin')?.addEventListener('click',()=>{
  setAuthFeedback('#registerFeedback','');
  $('#registerCard').hidden=true;
  $('#loginCard').hidden=false;
  $('#cloudEmail')?.focus();
});

$('#cloudPassword')?.addEventListener('keydown',e=>{if(e.key==='Enter' && !$('#cloudLogin')?.disabled)$('#cloudLogin')?.click()});
$('#regPassword')?.addEventListener('keydown',e=>{if(e.key==='Enter' && !$('#cloudRegister')?.disabled)$('#cloudRegister')?.click()});

$('#cloudLogout')?.addEventListener('click',async()=>{
  ++accountEpoch;
  await fetch('/api/cloud/logout',{method:'POST'});
  cloudAccount=null;
  resetAnalysis();accountSync=null;
  activeAccountId='guest';
  renderHistory();renderWatchlist();
  setAuthScreen(false);
  $('#cloudPassword').value='';
  $('#cloudEmail')?.focus();
});
$('#refreshAccount')?.addEventListener('click',loadCloudStatus);

async function loadDevices(){
  const box=$('#deviceList'),account=activeAccountId;
  if(!box)return;
  try{
    const r=await fetch('/api/cloud/devices');
    const d=await r.json();
    if(account!==activeAccountId)return;
    if(!r.ok)throw new Error(cloudError(d));
    box.innerHTML=(d.devices||[]).map(x=>`<div class="history-item"><div><strong>${escapeHtml(x.name)}</strong><small>${x.active?'ATIVO':'DESATIVADO'} · ${escapeHtml(x.device_uuid)}</small></div>${x.active?`<button class="ghost device-remove" data-id="${x.id}">Remover</button>`:''}</div>`).join('')||'<div class="empty">Nenhum dispositivo vinculado.</div>';
    $$('.device-remove').forEach(b=>b.addEventListener('click',async()=>{await fetch('/api/cloud/devices/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});await loadDevices()}));
  }catch(e){if(account!==activeAccountId)return;box.innerHTML='<div class="empty">Não foi possível carregar dispositivos.</div>'}
}

setAuthScreen(false);
loadCloudStatus();

// O Cloud mantém cada conta isolada, sem plano pago e sem cota mensal.
const _analysisSubmitNote=document.createElement('div');
_analysisSubmitNote.className='micro cloud-note';
_analysisSubmitNote.textContent='MarketAI Community · gratuito · open source · dados vinculados à sua conta.';
form?.querySelector('.wide')?.appendChild(_analysisSubmitNote);


let latestUpdate=null;
function vtuple(v){return String(v||'0').replace(/^v/i,'').split('.').map(x=>parseInt(x)||0)}
function newer(a,b){const x=vtuple(a),y=vtuple(b);for(let i=0;i<4;i++){if((x[i]||0)>(y[i]||0))return true;if((x[i]||0)<(y[i]||0))return false}return false}
async function checkUpdate(){try{const r=await fetch('/api/update/check');const d=await r.json();const current=($('#appVersion')?.textContent||'v1.0.2').replace('MarketAI','').trim();if(d.available&&newer(d.version,current)){latestUpdate=d;const b=$('#updateAvailable');b.hidden=false;b.textContent=`Atualizar para v${d.version}`;if(d.mandatory)setTimeout(()=>startUpdate(true),500)}}catch(e){}}
async function startUpdate(mandatory=false){if(!latestUpdate)return;if(!mandatory&&!confirm(`Instalar MarketAI v${latestUpdate.version}?\n\n${latestUpdate.notes||''}`))return;const b=$('#updateAvailable');b.disabled=true;b.textContent='Baixando atualização…';try{const r=await fetch('/api/update/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(latestUpdate)});const d=await r.json();if(!r.ok)throw new Error(d.message||d.detail||'Falha na atualização');alert(d.message||'Instalador iniciado.');}catch(e){alert(e.message);b.disabled=false;b.textContent=`Atualizar para v${latestUpdate.version}`}}
$('#updateAvailable')?.addEventListener('click',()=>startUpdate(false));setTimeout(checkUpdate,1800);


// ===================== MARKETAI INTELLIGENCE CORE =====================
function intelMoney(v){return v==null?'—':fmtBRL(Number(v))}
async function intelJson(url,opts={}){const r=await fetch(url,opts);let d={};try{d=await r.json()}catch{};if(!r.ok)throw new Error(d.message||d.detail||tr('Intelligence Core request failed'));return d}
async function loadIntelligence(){
  const radar=$('#intelRadar'), alerts=$('#intelAlerts');
  if(radar)radar.innerHTML=`<div class="empty">${escapeHtml(tr('Loading Radar…'))}</div>`; if(alerts)alerts.innerHTML=`<div class="empty">${escapeHtml(tr('Loading Sentinel…'))}</div>`;
  try{
    const account=activeAccountId;
    const [r,a,w]=await Promise.all([intelJson('/api/intelligence/radar'),intelJson('/api/intelligence/alerts'),intelJson('/api/intelligence/watches')]);
    if(account!==activeAccountId)return;
    updateProductSelectors(w.items.filter(x=>x.active));
    radar.innerHTML=(r.items||[]).length?(r.items||[]).slice(0,8).map((x,i)=>`<div class="intel-row"><b>#${i+1} ${escapeHtml(x.product_name)}</b><span>${x.market_score==null?escapeHtml(tr('Score blocked')):x.score+'/100'}</span><small>${intelMoney(x.median)} · ${escapeHtml(tr('trend'))} ${Number(x.price_trend_percent||0).toFixed(1)}% · ${x.collected_at?escapeHtml(new Date(x.collected_at).toLocaleString(appLocale())):''}</small></div>`).join(''):`<div class="empty">${escapeHtml(tr('There are no snapshots yet. Add products to Sentinel and run checks.'))}</div>`;
    const open=(a.items||[]).filter(x=>!x.acknowledged); alerts.innerHTML=open.length?open.slice(0,8).map(x=>{const text=window.MarketAlerts?.describe(x)||x;return `<div class="intel-row alert-${escapeAttr(x.severity)}"><b>${escapeHtml(text.title)}</b><small>${escapeHtml(text.message)}</small></div>`}).join(''):`<div class="empty">${escapeHtml(tr('No pending alerts.'))}</div>`;
  }catch(e){radar.innerHTML=`<div class="empty">${escapeHtml(e.message)}</div>`;alerts.innerHTML=`<div class="empty">${escapeHtml(tr('Sign in to your account to access Intelligence Core.'))}</div>`}
}
$('#intelRefresh')?.addEventListener('click',loadIntelligence);
$('#askCopilot')?.addEventListener('click',async()=>{
  const out=$('#copilotAnswer'),button=$('#askCopilot'),account=activeAccountId;
  const question=$('#copilotQuestion').value.trim();if(!question){out.textContent=tr('Enter a question.');return;}
  button.disabled=true;out.textContent=tr('Thinking with your data…');$('#copilotMode').textContent='';
  try{const target=$('#copilotTarget').value;const d=await intelJson('/api/intelligence/copilot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,watch_id:target||null,analysis_id:!target?currentAnalysis?.history_id:null,language:window.MarketI18n?.language?.()||'en'})});if(account!==activeAccountId)return;out.textContent=d.answer||tr('No answer.');$('#copilotMode').textContent=tr(d.mode==='ai'?'AI response using saved account data':'Deterministic response using saved account data');}catch(e){if(account===activeAccountId)out.textContent=e.message}finally{button.disabled=false}
});
$('#calcProfit')?.addEventListener('click',async()=>{const out=$('#profitOutput');out.textContent=tr('Calculating…');try{const d=await intelJson('/api/intelligence/profit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sale_price:num($('#profitPrice').value),unit_cost:num($('#profitCost').value),marketplace_fee_percent:num($('#profitFee').value),taxes_percent:num($('#profitTax').value),ads_percent:num($('#profitAds').value),payment_fee_percent:num($('#profitPayment').value),minimum_margin_percent:15})});out.innerHTML=`<strong>${intelMoney(d.net_profit)}</strong> ${escapeHtml(tr('net profit'))} · ${Number(d.net_margin_percent).toFixed(1)}% ${escapeHtml(tr('margin'))} · ROI ${Number(d.roi_percent).toFixed(1)}% · ${escapeHtml(tr('break-even'))} ${intelMoney(d.break_even_price)}`;}catch(e){out.textContent=e.message}});

$('#saveWatch')?.addEventListener('click',async()=>{
  if(!currentAnalysis||!currentFormSnapshot)return;
  const button=$('#saveWatch'),account=activeAccountId;button.disabled=true;
  $('#monitorFeedback').textContent=tr('Saving to Sentinel…');
  try{
    const payload={...currentFormSnapshot,product_name:currentAnalysis.product?.product_name||currentFormSnapshot.product_name,variant_text:currentFormSnapshot.variant_text||'',destination_country:currentFormSnapshot.destination_country||'BR',autopilot_enabled:false};
    await intelJson('/api/intelligence/watches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(account!==activeAccountId)return;
    $('#monitorFeedback').textContent=tr('Saved to your account. Sentinel collects while its worker is running.');setWorkflowStep('monitor');await syncAccountData(true);
  }catch(e){if(account===activeAccountId)$('#monitorFeedback').textContent=tr('Monitoring was not saved. Try again.')+' '+e.message}finally{button.disabled=false}
});

document.addEventListener('marketai:languagechange',()=>{
  try{
    health();
    if(currentAnalysis && !result.hidden) renderAnalysis(currentAnalysis);
    renderHistory();
    renderWatchlist();
    if(cloudAccount?.authenticated) loadCloudStatus();
  }catch{}
});

function setSyncStatus(message){
  for(const id of ['#historySyncStatus','#watchSyncStatus']) $(id).textContent=message;
}
function importableHistory(items){
  return items.slice(0,80).map(x=>({client_id:x.client_id||x.id||crypto.randomUUID(),date:x.date,name:x.name,
    recommended:x.recommended??null,score:x.score??null,marketMedian:x.marketMedian??null,mode:x.mode||'unavailable'}));
}
async function syncAccountData(force=false){
  if(activeAccountId==='guest')return;
  const account=activeAccountId;
  if(accountSync?.account===account){await accountSync.promise;if(!force||account!==activeAccountId)return;return syncAccountData();}
  const task={account,promise:null};accountSync=task;
  task.promise=(async()=>{
    setSyncStatus(tr('Syncing account data…'));
    try{
      const historyKey=`marketai-history-migrated:${account}`,watchKey=`marketai-watch-migrated:${account}`;
      if(!localStorage.getItem(historyKey)){
        const existing=readAccountItems('marketai-history');
        const legacy=existing.filter(x=>!x.id);
        if(legacy.length){
          const entries=importableHistory(legacy);
          legacy.forEach((x,i)=>{x.client_id=entries[i].client_id});
          writeAccountItems('marketai-history',existing);
          await intelJson('/api/history/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:entries})});
        }
        if(account!==activeAccountId)return;
        localStorage.setItem(historyKey,'1');
      }
      if(!localStorage.getItem(watchKey)){
        for(const item of readAccountItems('marketai-watch').filter(x=>!x.id)){
          if(account!==activeAccountId)return;
          await intelJson('/api/intelligence/watches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item.form,product_name:item.name,autopilot_enabled:false})});
        }
        if(account!==activeAccountId)return;
        localStorage.setItem(watchKey,'1');
      }
      const [history,watches]=await Promise.all([intelJson('/api/history'),intelJson('/api/intelligence/watches')]);
      if(account!==activeAccountId)return;
      writeAccountItems('marketai-history',history.items||[]);
      const active=(watches.items||[]).filter(x=>x.active);
      writeAccountItems('marketai-watch',active.map(x=>({id:x.id,name:x.product_name,variant:x.variant_text,country:x.country,
        date:x.latest?.date||null,score:x.latest?.score??null,recommended:x.latest?.recommended??null,median:x.latest?.median??null,
        form:{...x.settings,product_name:x.product_name,variant_text:x.variant_text,destination_country:x.country}})));
      renderHistory();renderWatchlist();updateProductSelectors(active);setSyncStatus(tr('Synced with your account.'));
    }catch(e){if(account===activeAccountId)setSyncStatus(tr('Offline or sync failed. Showing saved data from this device.')+' '+e.message)}
    finally{if(accountSync===task)accountSync=null;}
  })();
  return task.promise;
}
function updateProductSelectors(items){
  for(const [id,label] of [['#forecastTarget','Select a product'],['#copilotTarget','Latest analysis / account']]){
    const select=$(id),previous=select.value;
    select.innerHTML=`<option value="">${escapeHtml(tr(label))}</option>`+items.map(x=>`<option value="${escapeAttr(x.id)}">${escapeHtml([x.product_name,x.variant_text,x.country].filter(Boolean).join(' · '))}</option>`).join('');
    if(items.some(x=>x.id===previous))select.value=previous;
  }
}
async function showForecast(id){
  const out=$('#forecastOutput'),button=$('#loadForecast'),account=activeAccountId;
  if(!id){out.textContent=tr('Select a monitored product to see projections.');return;}
  button.disabled=true;out.textContent=tr('Loading forecast…');
  try{
    const d=await intelJson('/api/intelligence/forecast/'+encodeURIComponent(id));if(account!==activeAccountId)return;
    if(!d.available){out.textContent=tr('At least two valid snapshots collected at different times are required.');return;}
    out.innerHTML=`<p>${escapeHtml(tr(d.preliminary?'Preliminary estimate: limited history':'Projection based on saved snapshots'))}</p><p>${escapeHtml(tr('Collected at'))}: ${escapeHtml(new Date(d.last_collected_at).toLocaleString(appLocale()))}</p><div class="forecast-values">${Object.entries(d.forecast).map(([days,value])=>`<div><span>${days} ${escapeHtml(tr('days'))} · ${escapeHtml(new Date(d.forecast_dates[days]).toLocaleDateString(appLocale()))}</span><strong>${fmtBRL(value)}</strong></div>`).join('')}</div><p class="micro">${d.points} ${escapeHtml(tr('observations'))} · ${Number(d.history_days).toLocaleString(appLocale())} ${escapeHtml(tr('days of history'))}</p><p class="muted">${escapeHtml(tr('Linear extrapolation by collection date. Future prices are not guaranteed.'))}</p>`;
  }catch(e){if(account===activeAccountId)out.textContent=e.message}finally{button.disabled=false}
}
$('#loadForecast').addEventListener('click',()=>showForecast($('#forecastTarget').value));
$('#forecastTarget').addEventListener('change',()=>{$('#forecastOutput').textContent=tr('Select a monitored product to see projections.')});
function setWorkflowStep(step){
  $$('#workflowSteps li').forEach(el=>{el.classList.toggle('active',el.dataset.step===step);if(el.dataset.step===step)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')});
}
function resetAnalysis(){
  window.MarketCatalogBackup?.reset();
  window.MarketAlerts?.reset();
  window.MarketBatches?.reset();
  window.MarketCatalog?.reset();
  currentAnalysis=null;currentFormSnapshot=null;result.hidden=true;form.style.display='grid';
  if(currentPreviewURL)URL.revokeObjectURL(currentPreviewURL);
  currentPreviewURL='';imageInput.value='';preview.hidden=true;uploadPrompt.hidden=false;
  $('#copilotQuestion').value='';$('#profitOutput').textContent='—';$('#copilotAnswer').textContent='';$('#copilotMode').textContent='';$('#forecastOutput').textContent='';$('#monitorFeedback').textContent='';
  $('#intelRadar').textContent='';$('#intelAlerts').textContent='';updateProductSelectors([]);setSyncStatus('');setWorkflowStep('analyze');
}
function renderNextAction(d){
  const state=d.market.quality.state;
  $('#nextActionTitle').textContent=tr(state==='reliable'?'Compare margin, then monitor':'Improve the evidence');
  const messages={reliable:'Compare the price scenarios with your costs, then monitor this product.',ambiguous:'Specify the exact variant: model, capacity, volume or concentration.',insufficient:'Fewer than three compatible listings. Refine the product or retry with more sources.',no_match:'Review the name, brand and variant. The returned listings did not match.',unavailable:'No source returned market data. Retry later or review source access on the Cloud.'};
  $('#nextActionMessage').textContent=tr(messages[state]||messages.unavailable);
  $('#monitorFeedback').textContent='';
}
function renderEvidence(d){
  const m=d.market,e=d.evidence||{},costs=d.pricing.costs,rec=d.pricing.strategies.recommended;
  const date=m.checked_at?new Date(m.checked_at).toLocaleString(appLocale()):'—';
  $('#evidenceSummary').innerHTML=`<p><strong>${escapeHtml(tr('Recommendation evidence'))}</strong> · ${escapeHtml(tr('Collected at'))}: ${escapeHtml(date)}</p><p>${m.pricing_count||0} / ${m.raw_count||0} ${escapeHtml(tr('listings used'))} · ${m.discarded_count??m.discarded?.length??0} ${escapeHtml(tr('discarded listings'))} · ${m.quality.minimum_required||3} ${escapeHtml(tr('minimum required'))}</p><p>${escapeHtml(tr('Minimum price for target margin'))}: ${fmtBRL(costs.minimum_for_target_margin)} · ${escapeHtml(tr('Target margin'))}: ${Number(costs.desired_margin_percent||0).toLocaleString(appLocale())}%${rec?` · ${escapeHtml(tr('Estimated margin'))}: ${Number(rec.net_margin_percent).toLocaleString(appLocale())}%`:''}</p><p>${escapeHtml(tr('Listing prices are not completed sales. Product matching does not verify authenticity.'))}</p>${(e.currency_fallback||d.fx?.live===false)?`<p>${escapeHtml(tr('Currency conversion used a fallback rate. Review it before deciding.'))}</p>`:''}`;
}
$('#refineAnalysis').addEventListener('click',()=>{$('#newAnalysis').click();form.elements.variant_text.focus()});
$('#compareMargin').addEventListener('click',()=>{$('#simulatorCard').scrollIntoView({behavior:'smooth'});$('#priceSlider').focus();setWorkflowStep('compare')});
$('#inspectEvidence').addEventListener('click',()=>$('#compatibleEvidence').scrollIntoView({behavior:'smooth'}));


async function openSavedAnalysis(id){
  const account=activeAccountId;
  try{
    const data=await intelJson('/api/history/'+encodeURIComponent(id));
    if(account!==activeAccountId)return;
    if(!data.analysis)throw new Error(tr('Imported summary'));
    currentAnalysis=data.analysis;currentAnalysis.history_id=data.item.id;
    currentFormSnapshot=data.analysis.request;
    if(currentPreviewURL)URL.revokeObjectURL(currentPreviewURL);
    currentPreviewURL='';imageInput.value='';preview.hidden=true;uploadPrompt.hidden=false;
    Object.entries(currentFormSnapshot||{}).forEach(([key,value])=>{const input=form.elements[key];if(input)input.value=value??''});
    switchView('analyze');renderAnalysis(currentAnalysis);form.style.display='none';result.hidden=false;setWorkflowStep('compare');
  }catch(error){if(account===activeAccountId)alert(error.message)}
}
