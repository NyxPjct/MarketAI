from __future__ import annotations
import asyncio, os
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from app.services.fx import get_rate_to_brl
from app.services.market import filter_compatible_listings, split_price_outliers
from app.services.sources import search_ebay_live, search_google_shopping_live, search_mercado_livre_catalog, search_mercado_livre_live
from app.services.pricing import PricingInputs, build_pricing
from app.services.vision import identify_product

ML_SITES={"BR":("MLB","Mercado Livre Brasil"),"MX":("MLM","Mercado Libre México"),"AR":("MLA","Mercado Libre Argentina")}
EBAY_MARKETS={"US":("EBAY_US","eBay Estados Unidos"),"FR":("EBAY_FR","eBay França"),"DE":("EBAY_DE","eBay Alemanha"),"GB":("EBAY_GB","eBay Reino Unido")}
GOOGLE_SHOPPING_COUNTRIES={"BR","US","FR","DE","GB","MX","AR","CA","JP","KR"}
MIN_PRICING_LISTINGS=3

def _dedupe(items):
    seen=set(); out=[]
    for x in items:
        k=(x.get("source",""),x.get("url") or "",str(x.get("title","")).lower(),round(float(x.get("price",0)),2))
        if k not in seen: seen.add(k); out.append(x)
    return out

def _breakdown(listings):
    g=defaultdict(list)
    for x in listings:g[x.get("source","Outro")].append(float(x.get("price_brl",0)))
    return [{"source":s,"count":len(v),"min":round(min(v),2),"median":round(median(v),2),"average":round(sum(v)/len(v),2),"max":round(max(v),2)} for s,v in g.items() if v]

def _quality(state, raw, matched, used, blockers, avg, live_sources):
    if state=="reliable":
        conf="alta" if used>=8 and avg>=82 and live_sources>=2 else ("boa" if used>=5 and avg>=75 else "moderada")
        return {"state":state,"label":"Amostra compatível para cálculo","message":f"{used} anúncios compatíveis passaram pelos filtros. Confiança: {conf}.","confidence":conf,"blockers":[],"minimum_required":MIN_PRICING_LISTINGS,"average_match_score":round(avg,1)}
    labels={"ambiguous":"Produto ambíguo","insufficient":"Amostra insuficiente","no_match":"Nenhum anúncio compatível","unavailable":"Sem dados reais de mercado"}
    messages={"ambiguous":"Foram encontradas variantes diferentes e elas não serão misturadas.","insufficient":f"Há menos de {MIN_PRICING_LISTINGS} anúncios compatíveis.","no_match":f"Foram encontrados {raw} anúncios, mas nenhum passou pelo filtro.","unavailable":"Nenhuma fonte retornou anúncios reais; o MarketAI não fabrica preços."}
    return {"state":state,"label":labels[state],"message":messages[state],"confidence":"bloqueada" if state=="ambiguous" else "indisponível","blockers":blockers or ["Refine a variante ou tente outra fonte."],"minimum_required":MIN_PRICING_LISTINGS,"average_match_score":round(avg,1)}

def _advice(pricing,quality):
    minimum=pricing["costs"]["minimum_for_target_margin"]
    if quality["state"]!="reliable": return {"verdict":"DADOS DE MERCADO INSUFICIENTES","summary":quality["message"],"reasons":[f"Preço mínimo pelos custos: R$ {minimum:,.2f}."],"risks":quality.get("blockers") or []}
    score=pricing["opportunity"]["score"]
    if score>=80: v="VALE MUITO A PENA ANALISAR A COMPRA"
    elif score>=65:v="VALE A PENA"
    elif score>=45:v="VALE COM CAUTELA"
    else:v="NÃO ENTRARIA AGORA"
    return {"verdict":v,"summary":"Decisão baseada somente em anúncios compatíveis da variante informada.","reasons":["Mercado compatível encontrado e filtrado por variante."],"risks":[]}

async def run_analysis(fields:dict,image_bytes:bytes|None=None,image_content_type:str|None=None):
    def f(name,default=0.0):
        try:return float(fields.get(name,default) or default)
        except:return float(default)
    def i(name,default=1):
        try:return int(fields.get(name,default) or default)
        except:return int(default)
    product_name=str(fields.get("product_name") or "").strip(); variant_text=str(fields.get("variant_text") or "").strip(); gtin=str(fields.get("gtin") or "").strip()
    if not product_name: raise ValueError("product_name_required")
    quantity=max(1,i("quantity",1)); destination=str(fields.get("destination_country") or "BR").upper(); purchase_currency=str(fields.get("purchase_currency") or "BRL").upper()
    identity=await identify_product(product_name,variant_text,image_bytes,image_content_type)
    if gtin: identity["gtin"]=gtin
    fx=await get_rate_to_brl(purchase_currency); rate=float(fx["rate"])
    pricing_inputs=PricingInputs(purchase_cost_brl=f("purchase_cost")*rate,freight_brl=f("freight_total")*rate/quantity,import_cost_brl=f("import_cost_total")*rate/quantity,packaging_brl=f("packaging_unit"),other_costs_brl=f("other_costs_unit"),marketplace_fee_percent=f("marketplace_fee_percent",16),taxes_percent=f("taxes_percent",6),ads_percent=f("ads_percent",3),desired_margin_percent=f("desired_margin_percent",20))
    parts=[str(identity.get("brand") or ""),str(identity.get("model") or "") if str(identity.get("model") or "").lower() not in {"a confirmar","unknown"} else "",product_name,variant_text,str(identity.get("variant_summary") or "")]
    query=" ".join(dict.fromkeys(x.strip() for x in parts if x and x.strip())).strip()
    jobs=[]; catalog_job=None
    if destination in ML_SITES:
        site,name=ML_SITES[destination]; jobs.append(search_mercado_livre_live(query,site=site,source_name=name))
        if os.getenv("MERCADOLIVRE_ACCESS_TOKEN","").strip(): catalog_job=search_mercado_livre_catalog(query,site=site)
    if destination in EBAY_MARKETS:
        market,name=EBAY_MARKETS[destination]; jobs.append(search_ebay_live(query,marketplace=market,source_name=name,gtin=gtin))
    if destination in GOOGLE_SHOPPING_COUNTRIES: jobs.append(search_google_shopping_live(query,country=destination))
    results=await asyncio.gather(*jobs) if jobs else []; catalog=await catalog_job if catalog_job else {"items":[],"diagnostic":None}
    raw=[]; source_diags=[]
    for r in results: raw.extend(r.get("items") or []); source_diags.append(r.get("diagnostic") or {})
    raw=_dedupe(raw); live_sources=sum(1 for d in source_diags if d.get("status")=="ok" and int(d.get("returned") or 0)>0)
    cache={"BRL":{"rate":1.0}}; norm=[]
    for x in raw:
        cur=(x.get("currency") or "BRL").upper()
        if cur not in cache: cache[cur]=await get_rate_to_brl(cur)
        y=dict(x); y["price_brl"]=round(float(x["price"])*float(cache[cur]["rate"]),2); norm.append(y)
    compatible,rejected_match,ambiguity=filter_compatible_listings(norm,identity,product_name,variant_text=variant_text,gtin=gtin,strict=str(fields.get("match_mode") or "strict")!="balanced")
    avg=sum(x.get("match_score",0) for x in compatible)/len(compatible) if compatible else 0; clean,rejected_out=split_price_outliers(compatible); rejected=rejected_match+rejected_out
    state="unavailable" if not norm else ("no_match" if not compatible else ("ambiguous" if ambiguity.get("ambiguous") else ("insufficient" if len(clean)<MIN_PRICING_LISTINGS else "reliable")))
    quality=_quality(state,len(norm),len(compatible),len(clean),ambiguity.get("blockers"),avg,live_sources)
    pricing=build_pricing([x["price_brl"] for x in clean] if state=="reliable" else [],pricing_inputs)
    for x in clean: x["used_for_pricing"]=state=="reliable"
    return {"product":identity,"request":{k:fields.get(k) for k in fields},"fx":fx,"pricing":pricing,"advice":_advice(pricing,quality),"comparison":None,"market":{"live":live_sources>0,"reliable":state=="reliable","checked_at":datetime.now(timezone.utc).isoformat(),"live_source_count":live_sources,"quality":quality,"raw_count":len(norm),"matched_count":len(compatible),"pricing_count":len(clean) if state=="reliable" else 0,"discarded_count":len(rejected),"listings":sorted(clean if state=="reliable" else compatible,key=lambda x:(-x.get("match_score",0),x.get("price_brl",0)))[:40],"discarded":sorted(rejected,key=lambda x:(-x.get("match_score",0),x.get("price_brl",0)))[:60],"by_source":_breakdown(clean if state=="reliable" else compatible),"sources":source_diags,"query":query,"target_features":ambiguity.get("target_features") or {},"catalog_candidates":catalog.get("items") or []},"notes":["Análise executada pelo MarketAI Cloud com credenciais mantidas exclusivamente no servidor."]}
