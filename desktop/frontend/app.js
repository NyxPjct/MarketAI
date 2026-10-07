const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const fmtBRL = (n) => n == null || Number.isNaN(Number(n)) ? '—' : new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(Number(n));
const fmtMoney = (n,c='BRL') => { try { return new Intl.NumberFormat('pt-BR',{style:'currency',currency:c}).format(Number(n||0)); } catch { return `${Number(n||0).toFixed(2)} ${c}`; } };
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
    const labels=[];
    if(d.integrations?.mercadolivre_token) labels.push('ML autenticado');
    else labels.push('ML público');
    if(d.integrations?.ebay) labels.push('eBay');
    if(d.integrations?.google_shopping) labels.push('Shopping');
    if(d.integrations?.vision) labels.push('visão IA');
    $('#apiStatus').textContent = `${labels.join(' · ')} · v${d.version}`;
    $('.status-dot').classList.add('live');
  }catch{ $('#apiStatus').textContent = 'API offline'; }
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
  if(name==='history') renderHistory();
  if(name==='watchlist') renderWatchlist();
  if(name==='integrations') loadIntegrations();
  if(name==='settings') loadSettings();
}
$$('.nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));

const loadingSteps = [
  'Identificando produto, variante e atributos.',
  'Consultando apenas fontes reais disponíveis.',
  'Rejeitando kit, tester, decant e variantes incompatíveis.',
  'Validando volume, capacidade, potência e outliers.',
  'Calculando preço somente se a amostra for confiável.'
];

function snapshotForm(){
  const out={}; new FormData(form).forEach((v,k)=>{ if(!(v instanceof File)) out[k]=v; }); return out;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault(); result.hidden = true; form.style.display = 'none'; loading.hidden = false; currentFormSnapshot=snapshotForm();
  let i=0; const timer=setInterval(()=>{$('#loadingText').textContent=loadingSteps[(++i)%loadingSteps.length]},1100);
  try{
    const data=new FormData(form); const r=await fetch('/api/analyze',{method:'POST',body:data});
    if(!r.ok){let d={};try{d=await r.json()}catch{};const code=d.detail||'';if(r.status===401||r.status===402){switchView('account');throw new Error(r.status===401?'Entre na sua conta MarketAI para analisar produtos.':'Sua assinatura/teste não está ativo. Abra Minha conta para renovar ou ativar uma licença.')}if(r.status===403&&code==='device_not_authorized'){switchView('account');throw new Error('Este computador não está autorizado no seu plano. Remova outro dispositivo ou faça upgrade.')}if(r.status===429)throw new Error('Sua cota mensal de análises terminou. Faça upgrade do plano para continuar.');throw new Error(d.message||d.detail||'Não foi possível concluir a análise.')}
    const analysis=await r.json(); currentAnalysis=analysis; renderAnalysis(analysis); saveHistory(analysis); result.hidden=false; result.scrollIntoView({behavior:'smooth',block:'start'});loadCloudStatus();
  }catch(err){ alert('Não consegui concluir a análise.\n\n'+err.message); form.style.display='grid'; }
  finally{ clearInterval(timer); loading.hidden=true; }
});

$('#newAnalysis').addEventListener('click',()=>{result.hidden=true;form.style.display='grid';window.scrollTo({top:0,behavior:'smooth'})});

function featureSummary(f={}){
  const parts=[];
  if(f.concentration) parts.push(String(f.concentration).toUpperCase());
  if(f.volume_ml!=null) parts.push(`${Number(f.volume_ml).toLocaleString('pt-BR',{maximumFractionDigits:1})} ml`);
  if(f.capacity_gb!=null) parts.push(`${Number(f.capacity_gb)} GB`);
  if(f.power_w!=null) parts.push(`${Number(f.power_w)} W`);
  if(f.kit) parts.push('kit'); if(f.tester) parts.push('tester'); if(f.decant) parts.push('decant');
  if(f.refill) parts.push('refil'); if(f.sample) parts.push('amostra');
  return parts.join(' · ') || 'não identificada no título';
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
  const badge=$('#qualityBadge'); badge.textContent=q.state==='reliable'?'APROVADO PARA CÁLCULO':q.state==='ambiguous'?'VARIANTE AMBÍGUA':q.state==='insufficient'?'AMOSTRA PEQUENA':'SEM PREÇO CONFIÁVEL';
  badge.className=`quality-badge ${qualityClass(q.state)}`;
  $('#dataQualityCard').className=`card data-quality-card ${qualityClass(q.state)}`;
  $('#qualityCounts').textContent=`${d.market.raw_count} encontrados · ${d.market.matched_count} compatíveis · ${d.market.pricing_count} usados no preço`;
  $('#qualityBlockers').innerHTML=(q.blockers||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join('');
  $('#sourceStatus').innerHTML=(d.market.sources||[]).length
    ? d.market.sources.map(x=>{
        const cls=x.status==='ok'?'source-ok':(x.status==='not_configured'?'source-off':'source-warn');
        const status=x.status==='ok'?`${x.returned||0} resultado(s)`:sourceStatusLabel(x.status);
        const err=x.error?`<small>${escapeHtml(x.error)}</small>`:'';
        return `<span class="${cls}"><b>${escapeHtml(x.source)}</b>: ${escapeHtml(status)}${x.latency_ms?` · ${x.latency_ms} ms`:''}${err}</span>`;
      }).join('')
    : '<span>Nenhuma fonte de mercado disponível para este país.</span>';
}

function sourceStatusLabel(status){
  return ({not_configured:'não configurado',auth_required:'autenticação necessária',rate_limited:'limite de requisições',network_error:'erro de rede',upstream_error:'fonte indisponível',http_error:'erro HTTP',configured:'configurado',fallback:'contingência'})[status]||status||'indisponível';
}

function renderAnalysis(d){
  const p=d.product, pr=d.pricing, rec=pr.strategies.recommended, reliable=d.market.reliable;
  $('#productTitle').textContent=p.product_name||d.request.typed_name;
  $('#productMeta').textContent=[p.brand,p.model,p.variant_summary||p.variant,p.category].filter(x=>x && String(x).toLowerCase()!=='a confirmar').join(' · ') || 'Identificação básica';
  $('#productCodes').textContent=[d.request.gtin?`GTIN: ${d.request.gtin}`:'',d.request.ncm?`NCM: ${d.request.ncm}`:'',d.request.supplier_name?`Fornecedor: ${d.request.supplier_name}`:''].filter(Boolean).join(' · ')||'Sem códigos adicionais informados';
  $('#confidenceValue').textContent=`${p.confidence??0}%`; $('#confidenceBar').style.width=`${Math.max(0,Math.min(100,p.confidence||0))}%`;
  $('#resultThumb').innerHTML=currentPreviewURL?`<img src="${currentPreviewURL}" alt="produto">`:'AI';

  renderQuality(d);

  $('#scoreValue').textContent=reliable ? pr.opportunity.score : '—';
  $('#scoreLabel').textContent=reliable ? pr.opportunity.label : 'Score bloqueado até existir mercado confiável';
  $('#scoreLabel').style.color=reliable?(pr.opportunity.signal==='red'?'var(--red)':pr.opportunity.signal==='yellow'?'var(--yellow)':'var(--green)'):'var(--muted)';

  $('#marketMedian').textContent=reliable?fmtBRL(pr.market.median):'Sem mediana';
  $('#marketMedianCaption').textContent=reliable?`${pr.market.count} anúncio(s) usados no cálculo`:'nenhum preço fictício será usado';
  $('#recommendedPrice').textContent=rec?fmtBRL(rec.price):'BLOQUEADO';
  $('#recommendedCaption').textContent=rec?'equilíbrio entre margem e mercado compatível':`piso pelos seus custos: ${fmtBRL(pr.costs.minimum_for_target_margin)}`;
  $('#recommendedProfit').textContent=rec?fmtBRL(rec.net_profit):'—';
  $('#recommendedMargin').textContent=rec?`margem ${rec.net_margin_percent}% · ROI ${rec.roi_percent}%`:'sem lucro estimado de mercado';
  $('#unitCost').textContent=fmtBRL(pr.costs.unit_cost); $('#breakEven').textContent=`equilíbrio: ${fmtBRL(pr.costs.break_even)}`;

  $('#verdictTitle').textContent=d.advice.verdict; $('#verdictSummary').textContent=d.advice.summary;
  $('#verdictReasons').innerHTML=(d.advice.reasons.length?d.advice.reasons:['Nenhum ponto positivo adicional identificado.']).map(x=>`<li>${escapeHtml(x)}</li>`).join('');
  $('#verdictRisks').innerHTML=(d.advice.risks.length?d.advice.risks:['Nenhum alerta relevante nas premissas informadas.']).map(x=>`<li>${escapeHtml(x)}</li>`).join('');

  const strategyNames={fast_sale:['Venda rápida','entrada agressiva'],recommended:['Recomendado','melhor equilíbrio'],margin:['Mais margem','lucro ampliado'],premium:['Premium','posicionamento alto']};
  if(rec){
    $('#strategies').innerHTML=Object.entries(pr.strategies).map(([key,x])=>{if(!x)return ''; const [name,desc]=strategyNames[key];return `<div class="strategy ${key==='recommended'?'recommended':''}"><span>${name}</span><strong>${fmtBRL(x.price)}</strong><small>${desc}</small><small>Lucro: ${fmtBRL(x.net_profit)} · ${x.net_margin_percent}% · ROI ${x.roi_percent}%</small>${key==='recommended'?'<em>RECOMENDADO PELA IA</em>':''}</div>`}).join('');
  }else{
    const floor=pr.cost_floor;
    $('#strategies').innerHTML=`<div class="strategy cost-only"><span>Piso pelos seus custos</span><strong>${fmtBRL(floor.price)}</strong><small>Preço mínimo para atingir sua margem informada.</small><small>Lucro calculado: ${fmtBRL(floor.net_profit)} · ${floor.net_margin_percent}%</small><em>NÃO É PREÇO DE MERCADO</em></div><div class="empty compact strategy-empty">As quatro estratégias serão liberadas quando houver dados reais suficientes e uma variante sem ambiguidade.</div>`;
  }

  $('#fxCurrency').textContent=d.request.purchase_currency; $('#fxRate').textContent=Number(d.fx.rate).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:6}); $('#fxSource').textContent=d.fx.source; $('#fxDate').textContent=`Referência: ${d.fx.date||'—'}`; $('#fxLive').textContent=d.fx.live?'fonte ao vivo':'taxa de contingência';

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
  $('#marketCheckedAt').textContent=d.market.checked_at?`Coleta: ${new Date(d.market.checked_at).toLocaleString('pt-BR')} · ${d.market.live_source_count||0} fonte(s) respondendo · ${d.market.merchant_count||0} loja(s)/vendedor(es)`:'—';
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
  const items=JSON.parse(localStorage.getItem('marketai-history')||'[]');
  items.unshift({date:new Date().toISOString(),name:d.product.product_name||d.request.typed_name,recommended:rec?.price??null,score:d.pricing.opportunity.score??null,marketMedian:d.market.reliable?d.pricing.market.median:null,mode:d.market.quality.state});
  localStorage.setItem('marketai-history',JSON.stringify(items.slice(0,80)));
}

function renderHistory(){
  const items=JSON.parse(localStorage.getItem('marketai-history')||'[]');
  $('#historyList').innerHTML=items.length?items.map(x=>`<div class="history-item"><div><strong>${escapeHtml(x.name)}</strong><small>${new Date(x.date).toLocaleString('pt-BR')} · ${historyModeLabel(x.mode)}</small></div><div><small>MarketAI</small><div>${x.score==null?'—':x.score+'/100'}</div></div><div class="history-price">${x.recommended==null?'sem recomendação':fmtBRL(x.recommended)}</div></div>`).join(''):'<div class="empty">Nenhuma análise salva ainda.</div>';
  renderHistoryChart(items);
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
  el.innerHTML=`<div class="chart-title">${escapeHtml(latest)}</div><svg viewBox="0 0 ${w} ${h}" role="img"><line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" class="axis"/><polyline points="${line('marketMedian')}" class="line median-line"/><polyline points="${line('recommended')}" class="line rec-line"/>${data.map((x,i)=>{const [cx,cy]=pt(num(x.recommended),i);return `<circle cx="${cx}" cy="${cy}" r="4" class="dot"><title>${fmtBRL(x.recommended)} — ${new Date(x.date).toLocaleDateString('pt-BR')}</title></circle>`}).join('')}</svg><div class="legend"><span><i class="rec-key"></i>Preço recomendado</span><span><i class="med-key"></i>Mediana</span></div>`;
}
$('#clearHistory').addEventListener('click',()=>{localStorage.removeItem('marketai-history');renderHistory()});

$('#saveWatch').addEventListener('click',()=>{
  if(!currentAnalysis)return; const items=JSON.parse(localStorage.getItem('marketai-watch')||'[]'); const rec=currentAnalysis.pricing.strategies.recommended;
  const item={date:new Date().toISOString(),name:currentAnalysis.product.product_name||currentAnalysis.request.typed_name,score:currentAnalysis.pricing.opportunity.score??null,recommended:rec?.price??null,median:currentAnalysis.market.reliable?currentAnalysis.pricing.market.median:null,status:currentAnalysis.market.quality.state,form:currentFormSnapshot};
  const filtered=items.filter(x=>x.name!==item.name); filtered.unshift(item); localStorage.setItem('marketai-watch',JSON.stringify(filtered.slice(0,30))); $('#saveWatch').textContent='✓ Monitorado'; setTimeout(()=>$('#saveWatch').textContent='★ Monitorar',1400);
});
function renderWatchlist(){
  const items=JSON.parse(localStorage.getItem('marketai-watch')||'[]');
  $('#watchList').innerHTML=items.length?items.map((x,i)=>`<div class="history-item watch-item"><div><strong>${escapeHtml(x.name)}</strong><small>Salvo ${new Date(x.date).toLocaleString('pt-BR')} · ${historyModeLabel(x.status)}</small></div><div><small>Score</small><div>${x.score==null?'—':x.score+'/100'}</div></div><div class="history-price">${x.recommended==null?'sem preço':fmtBRL(x.recommended)}</div><button class="ghost reanalyze" data-i="${i}">Reanalisar</button></div>`).join(''):'<div class="empty">Nenhum produto monitorado.</div>';
  $$('.reanalyze').forEach(btn=>btn.addEventListener('click',()=>loadWatch(items[num(btn.dataset.i)])));
}
function loadWatch(item){ Object.entries(item.form||{}).forEach(([k,v])=>{const el=form.elements[k];if(el)el.value=v;}); switchView('analyze'); result.hidden=true; form.style.display='grid'; window.scrollTo({top:0,behavior:'smooth'}); }
$('#clearWatchlist').addEventListener('click',()=>{localStorage.removeItem('marketai-watch');renderWatchlist()});

$('#printReport').addEventListener('click',()=>window.print());
$('#exportCsv').addEventListener('click',()=>{
  if(!currentAnalysis)return; const d=currentAnalysis, rec=d.pricing.strategies.recommended;
  const rows=[['MarketAI v0.0'],['Produto',d.product.product_name||d.request.typed_name],['Variante',d.request.variant_text||d.product.variant_summary||''],['Qualidade',d.market.quality.label],['Score',d.pricing.opportunity.score??'bloqueado'],['Veredito',d.advice.verdict],['Custo real',d.pricing.costs.unit_cost],['Piso pela margem',d.pricing.costs.minimum_for_target_margin],['Preço recomendado',rec?.price??'indisponível'],['Lucro líquido',rec?.net_profit??'indisponível'],['Margem %',rec?.net_margin_percent??'indisponível'],[],['STATUS','Match','Fonte','Anúncio','Moeda','Preço original','Preço BRL','Motivo'],...d.market.listings.map(x=>['COMPATÍVEL',x.match_score,x.source,x.title,x.currency,x.price,x.price_brl,x.used_for_pricing?'USADO NO CÁLCULO':'']),...d.market.discarded.map(x=>['DESCARTADO',x.match_score,x.source,x.title,x.currency,x.price,x.price_brl,x.rejection_reason])];
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
$('#exportBackup')?.addEventListener('click',()=>downloadJson(`marketai-backup-${new Date().toISOString().slice(0,10)}.json`,{format:'MarketAIBackup',version:'0.0',exported_at:new Date().toISOString(),history:JSON.parse(localStorage.getItem('marketai-history')||'[]'),watchlist:JSON.parse(localStorage.getItem('marketai-watch')||'[]')}));
$('#importBackupBtn')?.addEventListener('click',()=>$('#importBackupFile').click());
$('#importBackupFile')?.addEventListener('change',async e=>{
  const file=e.target.files?.[0];if(!file)return;
  try{const d=JSON.parse(await file.text());if(d.format!=='MarketAIBackup')throw new Error('Arquivo não reconhecido.');if(Array.isArray(d.history))localStorage.setItem('marketai-history',JSON.stringify(d.history));if(Array.isArray(d.watchlist))localStorage.setItem('marketai-watch',JSON.stringify(d.watchlist));renderHistory();renderWatchlist();alert('Backup importado.');}catch(err){alert('Não foi possível importar o backup.\n\n'+err.message)}finally{e.target.value=''}
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
    if(!d.first_run_completed) $('#onboarding').hidden=false;
  }catch{}
}
async function completeOnboarding(goSettings){
  try{await fetch('/api/setup/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}catch{}
  $('#onboarding').hidden=true; if(goSettings)switchView('settings');
}
$('#onboardingConfigure')?.addEventListener('click',async()=>{await completeOnboarding(false);switchView('account');});
$('#onboardingLater')?.addEventListener('click',()=>completeOnboarding(false));
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


// ===================== MARKETAI CLOUD ACCOUNT =====================
let cloudAccount=null;
function cloudError(d){const c=d?.detail||d?.message||'';const map={active_recurring_subscription_must_be_canceled_first:'Você já possui uma assinatura recorrente ativa. Cancele a renovação atual antes de trocar de gateway.',payment_method_not_available_for_country:'Esse meio de pagamento não está disponível para o país selecionado.',pix_available_only_for_brazil:'Pix está disponível somente para cobrança no Brasil.'};return map[c]||c||'Não foi possível concluir a operação.'}
async function loadCloudStatus(){
  try{const r=await fetch('/api/cloud/status');const d=await r.json();cloudAccount=d;const logged=!!d.authenticated;
    $('#loginCard').hidden=logged;$('#registerCard').hidden=true;$('#accountCard').hidden=!logged;
    if(logged){const u=d.user||{},e=d.entitlement||{};$('#accountName').textContent=u.full_name||'Conta MarketAI';$('#accountEmail').textContent=u.email||'—';$('#accountPlan').textContent=e.plan_name||e.plan_code||'—';$('#accountRemaining').textContent=e.remaining??'—';$('#accountQuota').textContent=e.quota??'—';$('#accountStatus').textContent=e.trialing?'TESTE GRÁTIS':String(e.status||'—').toUpperCase();if($('#cancelSubscription'))$('#cancelSubscription').hidden=!e.auto_renew;await loadDevices();}
  }catch(e){cloudAccount={authenticated:false,error:e.message}}
}
async function doCloudAuth(path,payload){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(cloudError(d));await loadCloudStatus();return d}
$('#cloudLogin')?.addEventListener('click',async()=>{try{await doCloudAuth('/api/cloud/login',{email:$('#cloudEmail').value,password:$('#cloudPassword').value});alert('Conta conectada.');}catch(e){alert(e.message)}});
$('#cloudRegister')?.addEventListener('click',async()=>{try{await doCloudAuth('/api/cloud/register',{full_name:$('#regName').value,email:$('#regEmail').value,password:$('#regPassword').value});alert('Conta criada. Seu teste gratuito começou.');}catch(e){alert(e.message)}});
$('#showRegister')?.addEventListener('click',()=>{$('#loginCard').hidden=true;$('#registerCard').hidden=false});$('#showLogin')?.addEventListener('click',()=>{$('#registerCard').hidden=true;$('#loginCard').hidden=false});
$('#cloudLogout')?.addEventListener('click',async()=>{await fetch('/api/cloud/logout',{method:'POST'});await loadCloudStatus()});$('#refreshAccount')?.addEventListener('click',async()=>{try{await fetch('/api/cloud/sync-subscription',{method:'POST'})}catch{};await loadCloudStatus()});
let selectedPaymentMethod='';let paymentMethodsCache=[];let billingCurrency='BRL';
function moneyFmt(value,currency){try{return new Intl.NumberFormat('pt-BR',{style:'currency',currency:currency||'BRL'}).format(Number(value||0))}catch{return `${currency||''} ${Number(value||0).toFixed(2)}`}}
async function loadPaymentMethods(){
  const country=$('#billingCountry')?.value||'BR';const box=$('#paymentMethods');selectedPaymentMethod='';$('#billingMethodLabel').value='Selecione abaixo';
  try{const r=await fetch(`/api/cloud/payment-methods?country_code=${encodeURIComponent(country)}`);const d=await r.json();if(!r.ok)throw new Error(cloudError(d));paymentMethodsCache=d.methods||[];billingCurrency=d.currency||'USD';
    box.innerHTML=paymentMethodsCache.map(m=>`<button type="button" class="card integration payment-choice" data-method="${escapeHtml(m.id)}"><div class="integration-body"><div class="integration-title"><h3>${escapeHtml(m.name)}</h3><span class="integration-state ${m.recurring?'on':'warn'}">${escapeHtml(m.badge||'')}</span></div><p>${escapeHtml(m.description||'')}</p><small>${m.recurring?'Renovação automática':'Pagamento avulso / renovação manual'} · ${escapeHtml(m.currency||billingCurrency)}</small></div></button>`).join('')||'<div class="empty">Nenhum gateway configurado para este país.</div>';
    $$('.payment-choice').forEach(b=>b.addEventListener('click',()=>{selectedPaymentMethod=b.dataset.method;$$('.payment-choice').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');const m=paymentMethodsCache.find(x=>x.id===selectedPaymentMethod);billingCurrency=m?.currency||billingCurrency;$('#billingMethodLabel').value=m?.name||selectedPaymentMethod;loadPlans();}));
  }catch(e){box.innerHTML=`<div class="empty">Não foi possível carregar os meios de pagamento: ${escapeHtml(e.message)}</div>`}
}
async function loadPlans(){try{const country=$('#billingCountry')?.value||'BR';const cur=selectedPaymentMethod?(paymentMethodsCache.find(x=>x.id===selectedPaymentMethod)?.currency||billingCurrency):billingCurrency;const r=await fetch(`/api/cloud/plans?country_code=${encodeURIComponent(country)}&currency=${encodeURIComponent(cur||'')}`);const d=await r.json();billingCurrency=d.currency||billingCurrency;$('#cloudPlans').innerHTML=(d.plans||[]).map(p=>`<div class="card integration"><div class="integration-body"><div class="integration-title"><h3>${escapeHtml(p.name)}</h3><span class="integration-state on">${escapeHtml(moneyFmt(p.price??p.price_brl,p.currency||d.currency||'BRL'))}/mês</span></div><p>${p.analyses_per_month} análises/mês · ${p.device_limit} dispositivo(s)</p><button class="ghost plan-buy" data-plan="${escapeHtml(p.code)}">${selectedPaymentMethod?'Pagar com '+escapeHtml(paymentMethodsCache.find(x=>x.id===selectedPaymentMethod)?.name||selectedPaymentMethod):'Escolha o pagamento acima'}</button></div></div>`).join('');$$('.plan-buy').forEach(b=>b.addEventListener('click',()=>buyPlan(b.dataset.plan)));}catch(e){$('#cloudPlans').innerHTML='<div class="empty">Cloud indisponível.</div>'}}
async function buyPlan(code){if(!cloudAccount?.authenticated){switchView('account');alert('Entre na sua conta antes de assinar.');return}if(!selectedPaymentMethod){alert('Escolha primeiro o meio de pagamento.');return}try{const country=$('#billingCountry')?.value||'BR';const methodCurrency=paymentMethodsCache.find(x=>x.id===selectedPaymentMethod)?.currency||billingCurrency;const r=await fetch('/api/cloud/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan_code:code,payment_method:selectedPaymentMethod,country_code:country,currency:methodCurrency})});const d=await r.json();if(!r.ok)throw new Error(cloudError(d));const feed=$('#paymentFeedback');feed.hidden=false;
  if(d.payment_method==='pix'){
    feed.innerHTML=`<strong>Pix criado.</strong><br>${escapeHtml(d.expires_note||'Aguardando confirmação.')}${d.qr_code?`<div class="pix-code"><code>${escapeHtml(d.qr_code)}</code><br><button id="copyPix" class="ghost" type="button">Copiar Pix Copia e Cola</button></div>`:''}`;
    $('#copyPix')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(d.qr_code||'');alert('Código Pix copiado.')}catch{prompt('Copie o código Pix:',d.qr_code||'')}});
    if(d.checkout_url)await fetch('/api/app/open-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:d.checkout_url})});
    alert('Pix gerado. Após o pagamento, clique em Atualizar para confirmar a liberação.');
  }else if(d.checkout_url){await fetch('/api/app/open-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:d.checkout_url})});feed.textContent=`Checkout ${d.provider||selectedPaymentMethod} aberto no navegador. Depois da aprovação, volte ao MarketAI e clique em Atualizar.`;}
  else feed.textContent='Checkout criado, mas o provedor não retornou um link. Verifique a configuração do gateway.';
}catch(e){alert(e.message)}}
$('#billingCountry')?.addEventListener('change',async()=>{await loadPaymentMethods();await loadPlans()});
$('#activateLicense')?.addEventListener('click',async()=>{try{const r=await fetch('/api/cloud/license',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({license_key:$('#licenseKey').value})});const d=await r.json();if(!r.ok)throw new Error(cloudError(d));alert('Licença ativada.');await loadCloudStatus();}catch(e){alert(e.message)}});
async function loadDevices(){const box=$('#deviceList');try{const r=await fetch('/api/cloud/devices');const d=await r.json();if(!r.ok)throw new Error(cloudError(d));box.innerHTML=(d.devices||[]).map(x=>`<div class="history-item"><div><strong>${escapeHtml(x.name)}</strong><small>${x.active?'ATIVO':'DESATIVADO'} · ${escapeHtml(x.device_uuid)}</small></div>${x.active?`<button class="ghost device-remove" data-id="${x.id}">Remover</button>`:''}</div>`).join('')||'<div class="empty">Nenhum dispositivo.</div>';$$('.device-remove').forEach(b=>b.addEventListener('click',async()=>{await fetch('/api/cloud/devices/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});await loadDevices()}));}catch(e){box.innerHTML='<div class="empty">Não foi possível carregar dispositivos.</div>'}}
loadCloudStatus();loadPaymentMethods().then(loadPlans);

// Inform the user clearly when the commercial cloud blocks an analysis.
const _analysisSubmitNote=document.createElement('div');_analysisSubmitNote.className='micro cloud-note';_analysisSubmitNote.textContent='As análises comerciais são processadas no MarketAI Cloud e consomem a cota do seu plano.';form?.querySelector('.wide')?.appendChild(_analysisSubmitNote);


$('#cancelSubscription')?.addEventListener('click',async()=>{if(!confirm('Cancelar a renovação/assinatura do MarketAI?'))return;try{const r=await fetch('/api/cloud/cancel-subscription',{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(cloudError(d));alert('Assinatura cancelada.');await loadCloudStatus();}catch(e){alert(e.message)}});
let latestUpdate=null;
function vtuple(v){return String(v||'0').replace(/^v/i,'').split('.').map(x=>parseInt(x)||0)}
function newer(a,b){const x=vtuple(a),y=vtuple(b);for(let i=0;i<4;i++){if((x[i]||0)>(y[i]||0))return true;if((x[i]||0)<(y[i]||0))return false}return false}
async function checkUpdate(){try{const r=await fetch('/api/update/check');const d=await r.json();const current=($('#appVersion')?.textContent||'v0.0').replace('MarketAI','').trim();if(d.available&&newer(d.version,current)){latestUpdate=d;const b=$('#updateAvailable');b.hidden=false;b.textContent=`Atualizar para v${d.version}`;if(d.mandatory)setTimeout(()=>startUpdate(true),500)}}catch(e){}}
async function startUpdate(mandatory=false){if(!latestUpdate)return;if(!mandatory&&!confirm(`Instalar MarketAI v${latestUpdate.version}?\n\n${latestUpdate.notes||''}`))return;const b=$('#updateAvailable');b.disabled=true;b.textContent='Baixando atualização…';try{const r=await fetch('/api/update/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(latestUpdate)});const d=await r.json();if(!r.ok)throw new Error(d.message||d.detail||'Falha na atualização');alert(d.message||'Instalador iniciado.');}catch(e){alert(e.message);b.disabled=false;b.textContent=`Atualizar para v${latestUpdate.version}`}}
$('#updateAvailable')?.addEventListener('click',()=>startUpdate(false));setTimeout(checkUpdate,1800);
