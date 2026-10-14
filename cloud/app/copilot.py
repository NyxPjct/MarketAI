"""Question-driven fallback that only reports saved account evidence."""
from __future__ import annotations
import re
import unicodedata


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))


def analysis_context(analysis):
    if not analysis:
        return None
    market = analysis.get('market') or {}
    pricing = analysis.get('pricing') or {}
    return {
        'product': analysis.get('product'),
        'market': {key: market.get(key) for key in ('reliable', 'checked_at', 'quality', 'pricing_count')},
        'pricing': {key: pricing.get(key) for key in ('costs', 'strategies', 'market')},
    }


COPY = {
    'en': {
        'margin': 'Margin and profit', 'costs': 'Declared costs', 'alerts': 'Pending alerts', 'forecast': 'Forecast',
        'summary': 'Account evidence', 'missing': 'The selected product has no saved evidence for this question.',
        'unsupported': 'I can answer questions about margin, costs, alerts, forecasts and saved opportunities. Specify a product to focus the answer.',
        'choose': 'Select a monitored product to forecast.', 'limited': 'Preliminary estimate: fewer than five observations.',
        'projection': 'Linear extrapolation from collection dates; future prices are not guaranteed.',
        'days': 'days', 'collected': 'Collected at', 'profit': 'Net profit', 'net_margin': 'Net margin',
        'unit_cost': 'Unit cost', 'floor': 'Minimum price for target margin', 'fees': 'Variable fees',
        'price': 'Recommended price', 'median': 'Market median', 'empty_alerts': 'No pending alerts.',
        'blocked': 'Market recommendation is blocked; cost calculations are not market evidence.',
        'fallback': 'Deterministic answer from your saved data.', 'unknown': 'unavailable',
    },
    'pt-BR': {
        'margin': 'Margem e lucro', 'costs': 'Custos informados', 'alerts': 'Alertas pendentes', 'forecast': 'Previsão',
        'summary': 'Evidências da conta', 'missing': 'O produto selecionado não tem evidências salvas para essa pergunta.',
        'unsupported': 'Posso responder sobre margem, custos, alertas, previsões e oportunidades salvas. Especifique um produto para direcionar a resposta.',
        'choose': 'Selecione um produto monitorado para projetar preços.', 'limited': 'Estimativa preliminar: menos de cinco observações.',
        'projection': 'Extrapolação linear pelas datas de coleta; os preços futuros não são garantidos.',
        'days': 'dias', 'collected': 'Coletado em', 'profit': 'Lucro líquido', 'net_margin': 'Margem líquida',
        'unit_cost': 'Custo por unidade', 'floor': 'Preço mínimo para a margem desejada', 'fees': 'Taxas variáveis',
        'price': 'Preço recomendado', 'median': 'Mediana do mercado', 'empty_alerts': 'Nenhum alerta pendente.',
        'blocked': 'A recomendação de mercado está bloqueada; cálculos de custo não são evidência de mercado.',
        'fallback': 'Resposta determinística baseada nos seus dados salvos.', 'unknown': 'indisponível',
    },
    'de': {
        'margin': 'Marge und Gewinn', 'costs': 'Angegebene Kosten', 'alerts': 'Offene Warnungen', 'forecast': 'Prognose',
        'summary': 'Kontodaten', 'missing': 'Für dieses Produkt fehlen gespeicherte Daten zur Frage.',
        'unsupported': 'Ich beantworte Fragen zu Marge, Kosten, Warnungen, Prognosen und gespeicherten Chancen. Wähle ein Produkt.',
        'choose': 'Wähle ein beobachtetes Produkt für die Prognose.', 'limited': 'Vorläufige Schätzung: weniger als fünf Beobachtungen.',
        'projection': 'Lineare Extrapolation nach Erfassungsdatum; zukünftige Preise sind nicht garantiert.',
        'days': 'Tage', 'collected': 'Erfasst am', 'profit': 'Nettogewinn', 'net_margin': 'Nettomarge',
        'unit_cost': 'Stückkosten', 'floor': 'Mindestpreis für Zielmarge', 'fees': 'Variable Gebühren',
        'price': 'Empfohlener Preis', 'median': 'Marktmedian', 'empty_alerts': 'Keine offenen Warnungen.',
        'blocked': 'Marktempfehlung gesperrt; Kostenberechnungen sind keine Marktdaten.',
        'fallback': 'Deterministische Antwort aus gespeicherten Daten.', 'unknown': 'nicht verfügbar',
    },
    'es': {
        'margin': 'Margen y beneficio', 'costs': 'Costes declarados', 'alerts': 'Alertas pendientes', 'forecast': 'Pronóstico',
        'summary': 'Evidencias de la cuenta', 'missing': 'El producto seleccionado no tiene evidencias guardadas para esta pregunta.',
        'unsupported': 'Puedo responder sobre margen, costes, alertas, pronósticos y oportunidades guardadas. Selecciona un producto.',
        'choose': 'Selecciona un producto monitoreado para proyectar precios.', 'limited': 'Estimación preliminar: menos de cinco observaciones.',
        'projection': 'Extrapolación lineal por fechas de recogida; los precios futuros no están garantizados.',
        'days': 'días', 'collected': 'Recogido el', 'profit': 'Beneficio neto', 'net_margin': 'Margen neto',
        'unit_cost': 'Coste unitario', 'floor': 'Precio mínimo para el margen objetivo', 'fees': 'Comisiones variables',
        'price': 'Precio recomendado', 'median': 'Mediana de mercado', 'empty_alerts': 'No hay alertas pendientes.',
        'blocked': 'Recomendación de mercado bloqueada; los cálculos de costes no son evidencia de mercado.',
        'fallback': 'Respuesta determinista basada en datos guardados.', 'unknown': 'no disponible',
    },
    'fr': {
        'margin': 'Marge et bénéfice', 'costs': 'Coûts déclarés', 'alerts': 'Alertes en attente', 'forecast': 'Prévision',
        'summary': 'Données du compte', 'missing': 'Ce produit ne dispose pas de données enregistrées pour cette question.',
        'unsupported': 'Je peux répondre sur la marge, les coûts, les alertes, les prévisions et les opportunités enregistrées. Sélectionnez un produit.',
        'choose': 'Sélectionnez un produit surveillé pour la prévision.', 'limited': 'Estimation préliminaire : moins de cinq observations.',
        'projection': 'Extrapolation linéaire par dates de collecte ; les prix futurs ne sont pas garantis.',
        'days': 'jours', 'collected': 'Collecté le', 'profit': 'Bénéfice net', 'net_margin': 'Marge nette',
        'unit_cost': 'Coût unitaire', 'floor': 'Prix minimum pour la marge cible', 'fees': 'Frais variables',
        'price': 'Prix recommandé', 'median': 'Médiane du marché', 'empty_alerts': 'Aucune alerte en attente.',
        'blocked': 'Recommandation bloquée ; les calculs de coûts ne sont pas des données de marché.',
        'fallback': 'Réponse déterministe fondée sur vos données enregistrées.', 'unknown': 'indisponible',
    },
}

TERMS = {
    'margin': r'margin|margem|margen|marge|profit|lucro|beneficio|gewinn|benefice|roi',
    'costs': r'cost|custo|costo|cout|kosten|fee|tax|impost|frais|gebuhr|break.even|equilibrio|piso',
    'alerts': r'alert|alerta|warn|risco|risk|risque|riesgo|atencao|attention|achtung',
    'forecast': r'forecast|previs|proje|pronost|prognos|trend|tendenc|tendance|futur',
    'summary': r'opportun|oportun|chanc|resumo|summary|resume|overview|visao|produto|product|produit|produkt|precio|price|preco|preis|prix',
}


def deterministic_answer(question, context, language='en'):
    copy = COPY.get(language, COPY['en'])
    query = normalized(question)
    intents = [intent for intent, pattern in TERMS.items() if re.search(r'\b(?:' + pattern + ')', query)]
    if len(intents) > 1 and 'summary' in intents:
        intents.remove('summary')
    if not intents:
        return {'answer': copy['unsupported'], 'intents': [], 'evidence_used': []}
    analysis = context.get('analysis') or {}
    pricing = analysis.get('pricing') or {}
    costs = pricing.get('costs') or {}
    rec = (pricing.get('strategies') or {}).get('recommended') or {}
    watch = context.get('watch') or {}
    latest = watch.get('latest') or {}
    product = (analysis.get('product') or {}).get('product_name') or watch.get('product_name')
    date = (analysis.get('market') or {}).get('checked_at') or latest.get('date')
    evidence_used = []
    lines = []

    def money(value):
        return copy['unknown'] if value is None else f'BRL {float(value):.2f}'

    for intent in intents:
        lines.append(copy[intent] + ':')
        if intent == 'alerts':
            pending = [a for a in context.get('alerts', []) if not a.get('acknowledged') and
                       (not watch or a.get('watch_id') == watch['id'])]
            lines.extend(f"• {a['title']}: {a['message']}" for a in pending)
            if not pending:
                lines.append(copy['empty_alerts'])
            evidence_used.extend({'type': 'alert', 'id': a['id']} for a in pending)
        elif intent == 'forecast':
            projection = context.get('forecast') or {}
            if not watch:
                lines.append(copy['choose'])
            elif not projection.get('available'):
                lines.append(copy['missing'])
            else:
                lines.extend(f"• {h} {copy['days']}: {money(value)}" for h, value in projection['forecast'].items())
                lines.append(copy['projection'])
                if projection.get('preliminary'):
                    lines.append(copy['limited'])
                lines.append(f"{copy['collected']}: {projection['last_collected_at']}")
                evidence_used.append({'type': 'forecast', 'watch_id': watch['id']})
        elif intent in {'margin', 'costs'}:
            if not pricing and not latest:
                lines.append(copy['missing'])
            elif intent == 'costs':
                if not costs:
                    lines.append(copy['missing'])
                else:
                    lines.extend([f"{copy['unit_cost']}: {money(costs.get('unit_cost'))}",
                                  f"{copy['floor']}: {money(costs.get('minimum_for_target_margin'))}",
                                  f"{copy['fees']}: {costs.get('variable_rate_percent', copy['unknown'])}%"])
            else:
                margin = rec.get('net_margin_percent', latest.get('net_margin'))
                if margin is None:
                    lines.append(copy['blocked'])
                else:
                    lines.append(f"{copy['net_margin']}: {margin:.2f}%")
                    if rec.get('net_profit') is not None:
                        lines.append(f"{copy['profit']}: {money(rec['net_profit'])}")
                    lines.append(f"{copy['price']}: {money(rec.get('price', latest.get('recommended')))}")
        else:
            if product:
                lines.append(product)
                lines.append(f"{copy['median']}: {money((pricing.get('market') or {}).get('median') if (analysis.get('market') or {}).get('reliable') else latest.get('median'))}")
                if analysis and not (analysis.get('market') or {}).get('reliable'):
                    lines.append(copy['blocked'])
            elif context.get('radar'):
                lines.extend(f"• {x['product_name']}: {x['score']}/100 · {copy['median']}: {money(x.get('median'))}" for x in context['radar'] if x.get('market_score') is not None)
                evidence_used.extend({'type': 'snapshot', 'watch_id': x['watch_id']} for x in context['radar'] if x.get('market_score') is not None)
                if len(lines) == 1:
                    lines.append(copy['missing'])
            else:
                lines.append(copy['missing'])
    if product and any(i in intents for i in ('margin', 'costs', 'summary')):
        lines.insert(0, product)
        if date:
            lines.append(f"{copy['collected']}: {date}")
        if context.get('analysis_id'):
            evidence_used.append({'type': 'analysis', 'id': context['analysis_id']})
        elif watch and latest:
            evidence_used.append({'type': 'snapshot', 'watch_id': watch['id']})
    lines.append(copy['fallback'])
    return {'answer': '\n'.join(lines), 'intents': intents, 'evidence_used': evidence_used}
