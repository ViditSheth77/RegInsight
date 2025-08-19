import logging
from functools import lru_cache
from src.edgar.client import get

logger = logging.getLogger("resolve")
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

@lru_cache(maxsize=1)
def _ticker_index():
    # JSON is {"0": {"ticker":"AAPL","cik_str":320193,"title":"Apple Inc."}, ...}
    data = get(COMPANY_TICKERS_URL).json()
    idx = {}
    for _, rec in data.items():
        t = (rec.get("ticker") or "").upper().strip()
        cik = str(rec.get("cik_str") or "").strip()
        if t and cik:
            idx[t] = cik
    return idx

def resolve_cik(ticker: str) -> str | None:
    try:
        return _ticker_index().get((ticker or "").upper().strip())
    except Exception as e:
        logger.warning("CIK resolve failed for %s: %s", ticker, e)
        return None
