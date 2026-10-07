from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Dict, Optional

import httpx

# Contingency fallbacks are only used when the official API is unavailable.
# They are NEVER presented as live rates in the UI.
FALLBACK_TO_BRL = {
    "BRL": 1.0,
    "USD": 5.30,
    "EUR": 6.15,
    "CNY": 0.74,
    "JPY": 0.036,
    "GBP": 7.05,
    "CAD": 3.82,
    "ARS": 0.0037,
    "MXN": 0.29,
    "KRW": 0.0038,
}

BCB_BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"


def _currency_alias(code: str) -> str:
    # BCB PTAX uses ISO-like symbols for the currencies supported by the service.
    return code.upper().strip()


async def get_rate_to_brl(currency: str) -> Dict:
    code = currency.upper().strip()
    if code == "BRL":
        return {"rate": 1.0, "source": "BRL", "live": True, "date": str(date.today())}

    target = _currency_alias(code)
    timeout = float(os.getenv("HTTP_TIMEOUT", "8"))

    # Ask for the latest available closing bulletin in a 10-day window, which
    # naturally handles weekends and holidays.
    end = date.today()
    start = end - timedelta(days=10)
    start_s = start.strftime("%m-%d-%Y")
    end_s = end.strftime("%m-%d-%Y")
    url = (
        f"{BCB_BASE}/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@moeda='{target}'&@dataInicial='{start_s}'&@dataFinalCotacao='{end_s}'"
        "&$top=100&$orderby=dataHoraCotacao%20desc&$format=json"
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            rows = r.json().get("value", [])
            if rows:
                row = rows[0]
                rate = float(row.get("cotacaoVenda") or row.get("cotacaoCompra") or 0)
                if rate > 0:
                    return {
                        "rate": rate,
                        "source": "Banco Central do Brasil — PTAX",
                        "live": True,
                        "date": row.get("dataHoraCotacao", str(end)),
                    }
    except Exception:
        pass

    fallback = float(os.getenv(f"FALLBACK_FX_{code}_BRL", FALLBACK_TO_BRL.get(code, 1.0)))
    return {
        "rate": fallback,
        "source": "Taxa de contingência (PTAX indisponível)",
        "live": False,
        "date": str(date.today()),
    }
