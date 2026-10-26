/* Per-product rules shared by manual collection and the Cloud Sentinel. */
(() => {
  'use strict';
  let generation=0,watch=null,revision=0,busy=false;
  const valid=(account,version)=>account===activeAccountId&&version===generation;
  const ids={price_enabled:'#alertPriceEnabled',price_change_percent:'#alertPricePercent',price_direction:'#alertPriceDirection',
    margin_enabled:'#alertMarginEnabled',minimum_margin_percent:'#alertMarginPercent',stale_enabled:'#alertStaleEnabled',
    stale_after_hours:'#alertStaleHours',cooldown_hours:'#alertCooldownHours'};
  const feedback=message=>{$('#alertRulesFeedback').textContent=message;};
  function buttons(){ $('#alertRulesSave').disabled=busy||!watch;for(const id of Object.values(ids))$(id).disabled=busy; }
  async function request(url,options={}){
    const response=await fetch(url,options);let data={};try{data=await response.json()}catch{}
    if(!response.ok)throw new Error(tr(data.detail==='alert_rules_conflict'?'Alert rules changed on another device. Close and reopen this editor.':
      response.status===404?'Alert rules unavailable. Refresh the products or update the Cloud.':'Could not load or save alert rules. Check the limits and try again.'));
    return data;
  }
  async function open(id){
    const account=activeAccountId,version=++generation;watch=null;busy=true;buttons();feedback(tr('Loading alert rules…'));$('#alertRulesProduct').textContent='';
    if(!$('#alertRulesDialog').open)$('#alertRulesDialog').showModal();
    try{
      const data=await request(`/api/intelligence/watches/${encodeURIComponent(id)}/alert-rules`);
      if(!valid(account,version))return;
      watch=id;revision=data.revision;$('#alertRulesProduct').textContent=data.product_name;
      for(const [key,selector] of Object.entries(ids)){const input=$(selector);if(input.type==='checkbox')input.checked=data.rules[key];else input.value=data.rules[key];}
      feedback('');
    }catch(error){if(valid(account,version))feedback(error.message)}finally{if(valid(account,version)){busy=false;buttons()}}
  }
  $('#alertRulesForm').addEventListener('submit',async event=>{
    event.preventDefault();if(!watch||busy)return;
    const rules={};for(const [key,selector] of Object.entries(ids)){const input=$(selector);rules[key]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;}
    const account=activeAccountId,version=generation,id=watch;busy=true;buttons();feedback(tr('Saving alert rules…'));
    try{
      const data=await request(`/api/intelligence/watches/${encodeURIComponent(id)}/alert-rules`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,rules})});
      if(!valid(account,version))return;revision=data.revision;feedback(tr('Alert rules saved to your account. They apply to future checks.'));
    }catch(error){if(valid(account,version))feedback(error.message)}finally{if(valid(account,version)){busy=false;buttons()}}
  });
  $('#alertRulesClose').addEventListener('click',()=>$('#alertRulesDialog').close());
  $('#alertRulesDialog').addEventListener('close',()=>{++generation;watch=null;busy=false;buttons()});
  function reset(){++generation;watch=null;busy=false;$('#alertRulesDialog').close();$('#alertRulesForm').reset();$('#alertRulesProduct').textContent='';feedback('');buttons();}
  function describe(alert){
    const d=alert.details;if(!d)return {title:alert.title,message:alert.message};
    const percent=value=>Number(value).toLocaleString(appLocale(),{maximumFractionDigits:2})+'%';
    if(alert.kind==='price_move')return {title:tr('Market price change'),message:`${d.product_name}: ${percent(d.change_percent)} · ${tr('Median')}: ${fmtBRL(d.median)}`};
    if(alert.kind==='margin')return {title:tr('Margin below threshold'),message:`${d.product_name}: ${tr('Estimated margin')}: ${percent(d.margin_percent)} · ${tr('Minimum net margin (%)')}: ${Number(d.threshold).toLocaleString(appLocale())}`};
    if(alert.kind==='stale_data')return {title:tr('No recent valid collection'),message:`${d.product_name}: ${Number(d.hours).toLocaleString(appLocale())} ${tr('hours without valid data')} · ${d.never_collected?tr('No valid collections yet'):new Date(d.last_valid_at).toLocaleString(appLocale())}`};
    if(alert.kind==='source_error')return {title:tr('Product collection failed'),message:`${d.product_name}: ${tr('Try another collection. No market values were invented.')}`};
    return {title:alert.title,message:alert.message};
  }
  window.MarketAlerts={open,reset,describe};
})();
