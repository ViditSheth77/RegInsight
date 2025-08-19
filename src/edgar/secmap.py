import time
import threading
from typing import Tuple, Optional, Dict

from src.edgar.client import get

# In-memory cache for ticker->CIK and CIK->ticker maps
_CACHE_LOCK = threading.Lock()
_TICKER_TO_CIK: Dict[str, str] = {}
_CIK_TO_TICKER: Dict[str, str] = {}
_LAST_LOAD = 0.0
_TTL_SECONDS = 60 * 60 * 6  # refresh every 6 hours

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

def _load_maps(force: bool = False) -> None:
    global _LAST_LOAD, _TICKER_TO_CIK, _CIK_TO_TICKER
    now = time.time()
    if not force and (now - _LAST_LOAD) < _TTL_SECONDS and _TICKER_TO_CIK:
        return
    # company_tickers.json -> { "0": {"ticker":"AAPL","cik_str":320193,"title":"Apple Inc."}, ... }
    j = get(SEC_TICKERS_URL).json()
    t2c, c2t = {}, {}
    for _, row in j.items():
        t = (row.get("ticker") or "").upper().strip()
        c = str(row.get("cik_str") or "").strip()
        if not t or not c:
            continue
        c = c.zfill(10)  # normalize
        t2c[t] = c
        c2t[c] = t
    with _CACHE_LOCK:
        _TICKER_TO_CIK = t2c
        _CIK_TO_TICKER = c2t
        _LAST_LOAD = now

def resolve(identifier: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Accepts either a TICKER or a CIK and returns (cik, ticker).
    Returns (None, None) if not found.
    """
    if not identifier:
        return None, None
    _load_maps()
    s = identifier.strip().upper()
    # If user passed a 10-digit CIK (or close), normalize and try reverse map
    if s.isdigit():
        cik = s.zfill(10)
        with _CACHE_LOCK:
            ticker = _CIK_TO_TICKER.get(cik)
        return (cik, ticker)
    # else treat as ticker
    with _CACHE_LOCK:
        cik = _TICKER_TO_CIK.get(s)
    return (cik, s if cik else None)
