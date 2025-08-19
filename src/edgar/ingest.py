import argparse, logging, re
from urllib.parse import urljoin
from sqlalchemy import text as sqltext
from bs4 import BeautifulSoup

from src.db import Session, init_db
from src.edgar.client import get
from src.edgar.parsing import html_to_text, split_sections
from src.config import MAX_DOC_CHARS, MAX_SECTION_CHARS
from src.logging_conf import setup_logging

setup_logging()
logger = logging.getLogger("ingest")

BASE = "https://data.sec.gov"

# -------- Main vs Exhibit heuristics --------
MAIN_FORM_TOKENS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "8-K", "20-F", "6-K"}
EXHIBIT_PAT = re.compile(r"(ex[-_\s]?\d+(\.\d+)?)|exhibit|\.xml$|xsd$|cal\.|def\.|lab\.|pre\.", re.I)

def is_exhibit(filename: str = "", description: str = "", doc_type: str = "") -> bool:
    name = (filename or "").lower()
    desc = (description or "").lower()
    typ  = (doc_type or "").lower()
    if "exhibit" in name or EXHIBIT_PAT.search(name): return True
    if "exhibit" in desc: return True
    if typ.startswith("ex-") or typ.startswith("exhibit"): return True
    if typ.startswith("ex") and any(ch.isdigit() for ch in typ): return True
    return False

def is_html_like(name: str) -> bool:
    n = (name or "").lower()
    return n.endswith(".htm") or n.endswith(".html")

def looks_ixbrl(name: str) -> bool:
    n = (name or "").lower()
    return ("ix" in n) or ("ixbrl" in n)

def mentions_form(name: str, desc: str, doc_type: str) -> bool:
    n = (name or "").lower()
    d = (desc or "").lower()
    t = (doc_type or "").upper()
    if t in MAIN_FORM_TOKENS: return True
    if "10-q" in n or "10-k" in n or "8-k" in n or "20-f" in n or "6-k" in n: return True
    if "10-q" in d or "10-k" in d or "8-k" in d or "20-f" in d or "6-k" in d: return True
    if re.search(r"\b(10q|10k|8k|20f|6k)\b", n): return True
    return False

def is_main_filing(filename: str = "", description: str = "", doc_type: str = "") -> bool:
    if is_exhibit(filename, description, doc_type): return False
    if not is_html_like(filename): return False
    return mentions_form(filename, description, doc_type) or looks_ixbrl(filename)

def pick_main_document(docs):
    if not docs: return None
    strong = [d for d in docs if is_main_filing(d.get("name"), d.get("description",""), d.get("type","")) and looks_ixbrl(d.get("name",""))]
    if strong: return max(strong, key=lambda d: int(d.get("size") or 0))
    plain = [d for d in docs if is_main_filing(d.get("name"), d.get("description",""), d.get("type",""))]
    if plain: return max(plain, key=lambda d: int(d.get("size") or 0))
    fall = [d for d in docs if is_html_like(d.get("name","")) and not is_exhibit(d.get("name",""), d.get("description",""), d.get("type",""))]
    if fall: return max(fall, key=lambda d: int(d.get("size") or 0))
    return None

# -------- SEC fetch utils --------
def latest_filings_for_cik(cik: str, forms=("10-K","10-Q"), limit=1):
    j = get(f"{BASE}/submissions/CIK{cik.zfill(10)}.json").json()
    rec = j.get("filings", {}).get("recent", {})
    out = []
    for form, date, acc in zip(rec.get("form",[]), rec.get("filingDate",[]), rec.get("accessionNumber",[])):
        if (not forms) or (form in forms):
            nodash = acc.replace("-", "")
            base_dir = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/"
            index_url = f"{base_dir}{acc}-index.html"
            out.append({
                "form": form, "date": date, "accession": acc,
                "nodash": nodash, "index_url": index_url, "base_dir": base_dir
            })
            if len(out) >= limit: break
    return out

def get_index_json(base_dir: str):
    j = get(urljoin(base_dir, "index.json")).json()
    items = j.get("directory", {}).get("item", []) or []
    for it in items: it.setdefault("description", "")
    for it in items: it.setdefault("href", it.get("href") or it.get("name"))
    return items

def parse_index_html(index_url: str):
    html = get(index_url).text
    soup = BeautifulSoup(html, "lxml")
    docs = []
    for tbl in soup.find_all("table"):
        header = tbl.find("tr")
        if not header: continue
        head_text = " ".join((header.get_text(" ", strip=True) or "").lower().split())
        if "document" not in head_text or "type" not in head_text: continue
        for tr in tbl.find_all("tr")[1:]:
            tds = tr.find_all(["td","th"])
            if len(tds) < 2: continue
            link = tds[0].find("a")
            name, href = None, None
            if link and link.get("href"):
                href = link["href"].strip()
                name = (link.get_text(" ", strip=True) or "").strip()
            dtype = (tds[1].get_text(" ", strip=True) or "").strip() if len(tds) >= 2 else ""
            desc  = (tds[2].get_text(" ", strip=True) or "").strip() if len(tds) >= 3 else ""
            size = 0
            try:
                if len(tds) >= 4:
                    stxt = (tds[-1].get_text(" ", strip=True) or "").lower()
                    m = re.search(r"([\d,]+)", stxt)
                    if m: size = int(m.group(1).replace(",", ""))
            except: size = 0
            if name and href:
                docs.append({"name": name, "href": href, "type": dtype, "size": size, "description": desc})
    return docs

def fetch_doc_catalog(base_dir: str, index_url: str):
    docs = []
    try: docs = get_index_json(base_dir)
    except Exception as e: logger.debug("index.json not usable: %s", e)
    if not docs:
        try: docs = parse_index_html(index_url)
        except Exception as e: logger.debug("parse index html failed: %s", e); docs = []
    return [d for d in docs if d.get("name") and d.get("href")]

# -------- Ingestion --------
def ingest_one(cik: str, ticker: str, limit=1, forms=("10-K","10-Q")):
    sess = Session()
    try:
        metas = latest_filings_for_cik(cik, forms=forms, limit=limit)
        for meta in metas:
            docs = fetch_doc_catalog(meta["base_dir"], meta["index_url"])
            if not docs:
                logger.warning("No docs for %s %s", ticker, meta["date"]); continue

            main_doc = pick_main_document(docs)
            if not main_doc:
                logger.warning("Main %s not found for %s %s", meta["form"], ticker, meta["date"]); continue

            # MAIN
            main_url  = urljoin(meta["base_dir"], main_doc["href"])
            main_html = get(main_url).text
            main_text = html_to_text(main_html)[:MAX_DOC_CHARS]

            filing_main_id = sess.execute(sqltext("""
              INSERT INTO filings_main (cik, ticker, form, filing_date, accession, source_url, filename, raw_text)
              VALUES (:cik,:ticker,:form,:date,:acc,:url,:fn,:txt)
              ON CONFLICT (accession) DO UPDATE
                SET ticker      = EXCLUDED.ticker,
                    form        = EXCLUDED.form,
                    filing_date = EXCLUDED.filing_date,
                    source_url  = EXCLUDED.source_url,
                    filename    = EXCLUDED.filename,
                    raw_text    = EXCLUDED.raw_text
              RETURNING id
            """), dict(
                cik=cik, ticker=ticker.upper(), form=meta["form"], date=meta["date"],
                acc=meta["accession"], url=main_url, fn=main_doc.get("name"), txt=main_text
            )).scalar()

            # Sections (simple split)
            for name, sec_txt in split_sections(main_text):
                sess.execute(sqltext("""
                  INSERT INTO sections_main (filing_id, name, text)
                  VALUES (:fid,:name,:txt)
                """), dict(fid=filing_main_id, name=name, txt=sec_txt[:MAX_SECTION_CHARS]))

            # EXHIBITS
            for d in docs:
                if d is main_doc: continue
                if is_exhibit(d.get("name",""), d.get("description",""), d.get("type","")):
                    ex_url = urljoin(meta["base_dir"], d["href"])
                    ex_text = ""
                    try:
                        ex_html = get(ex_url).text
                        ex_text = html_to_text(ex_html)[:MAX_DOC_CHARS]
                    except Exception as e:
                        logger.debug("Exhibit fetch failed %s: %s", ex_url, e)
                    sess.execute(sqltext("""
                      INSERT INTO filings_exhibits
                        (filing_accession, cik, ticker, form, filing_date,
                         filename, url, doc_type, description, size, text)
                      VALUES
                        (:acc,:cik,:ticker,:form,:date,
                         :fn,:url,:dtype,:desc,:size,:txt)
                      ON CONFLICT DO NOTHING
                    """), dict(
                        acc=meta["accession"], cik=cik, ticker=ticker.upper(), form=meta["form"],
                        date=meta["date"], fn=d.get("name"), url=ex_url, dtype=d.get("type"),
                        desc=d.get("description",""), size=int(d.get("size") or 0), txt=ex_text
                    ))

            logger.info("Ingested MAIN & exhibits for %s %s %s", ticker, meta["form"], meta["date"])
        sess.commit()
    finally:
        sess.close()

if __name__ == "__main__":
    init_db()
    ap = argparse.ArgumentParser()
    ap.add_argument("--cik", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--forms", type=str, default="10-K,10-Q",
                    help="Comma-separated list, e.g. '10-K,10-Q,8-K,20-F'")
    args = ap.parse_args()
    forms = tuple([s.strip() for s in args.forms.split(",") if s.strip()])
    ingest_one(args.cik, args.ticker, args.limit, forms=forms)
