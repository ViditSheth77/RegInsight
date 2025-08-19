import requests
from tenacity import retry, wait_exponential, stop_after_attempt
from src.config import SEC_USER_AGENT

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": SEC_USER_AGENT})

@retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(5))
def get(url: str, **kw):
    r = SESSION.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r
