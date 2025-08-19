from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import text as sqltext

from src.db import Session
from src.edgar.secmap import resolve as resolve_cik_ticker
from src.edgar.ingest import ingest_one  # on-demand ingest

app = FastAPI(title="RegInsight API")

# ---------- helpers ----------
def _query_main(sess: Session, ticker: Optional[str], form: Optional[str], limit: int):
    base = """
        SELECT id, cik, ticker, form, filing_date, accession, source_url, filename
        FROM filings_main
    """
    where = []
    params = {"lim": limit}
    if ticker:
        where.append("ticker = :t")
        params["t"] = ticker.upper()
    if form:
        where.append("form = :f")
        params["f"] = form
    if where:
        base += " WHERE " + " AND ".join(where)
    base += " ORDER BY filing_date DESC LIMIT :lim"
    return [dict(r) for r in sess.execute(sqltext(base), params).mappings().all()]

# ---------- main listings (auto-ingest if empty) ----------
@app.get("/filings/main")
def filings_main(
    identifier: Optional[str] = Query(None, description="Ticker or CIK"),
    ticker: Optional[str] = Query(None, description="(Legacy) ticker"),
    form: Optional[str] = Query(None, description="e.g., 10-Q, 10-K, 8-K"),
    forms: Optional[str] = Query(None, description="Comma-separated forms, e.g. '10-K,10-Q,8-K'"),
    limit: int = Query(20, ge=1, le=100),
    auto_ingest: bool = Query(True, description="If no rows found, fetch from SEC on the fly")
):
    ident = (identifier or ticker or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="Provide 'identifier' (ticker or CIK)")

    cik, tick = resolve_cik_ticker(ident)
    if not cik:
        raise HTTPException(status_code=404, detail="Unknown identifier (not in SEC ticker list)")

    sess = Session()
    try:
        rows = _query_main(sess, tick, form, limit)
        if rows:
            return rows

        if not auto_ingest:
            return rows

        # decide forms to ingest
        if forms:
            ingest_forms = [f.strip() for f in forms.split(",") if f.strip()]
        elif form:
            ingest_forms = [form]
        else:
            ingest_forms = ["10-K", "10-Q", "8-K"]

        ingest_one(cik=cik, ticker=tick or "", limit=1, forms=tuple(ingest_forms))
        return _query_main(sess, tick, form, limit)
    finally:
        sess.close()

# ---------- single main filing by id ----------
@app.get("/filings/main/{fid}")
def filing_main(fid: int):
    sess = Session()
    try:
        f = sess.execute(sqltext("""
            SELECT id, cik, ticker, form, filing_date, accession, source_url, filename
            FROM filings_main
            WHERE id = :fid
        """), {"fid": fid}).mappings().first()

        if not f:
            raise HTTPException(status_code=404, detail="Main filing not found")

        secs = sess.execute(sqltext("""
            SELECT id, name, LEFT(text, 3000) AS preview
            FROM sections_main
            WHERE filing_id = :fid
            ORDER BY id
        """), {"fid": fid}).mappings().all()

        return {"filing": dict(f), "sections": [dict(s) for s in secs]}
    finally:
        sess.close()

# ---------- latest main filing (optional form) ----------
@app.get("/filings/main/latest")
def latest_main_filing(
    identifier: str = Query(..., description="Ticker or CIK"),
    form: Optional[str] = Query(None, description="10-Q, 10-K, 8-K"),
    auto_ingest: bool = Query(True)
):
    cik, tick = resolve_cik_ticker(identifier)
    if not cik:
        raise HTTPException(status_code=404, detail="Unknown identifier (not in SEC ticker list)")

    sess = Session()
    try:
        row = sess.execute(sqltext("""
            SELECT id, cik, ticker, form, filing_date, accession, source_url, filename
            FROM filings_main
            WHERE ticker = :t
              AND (:f IS NULL OR form = :f)
            ORDER BY filing_date DESC
            LIMIT 1
        """), {"t": tick, "f": form}).mappings().first()

        if row:
            return dict(row)

        if not auto_ingest:
            raise HTTPException(status_code=404, detail="No main filing found")

        ingest_forms = [form] if form else ["10-K", "10-Q", "8-K"]
        ingest_one(cik=cik, ticker=tick or "", limit=1, forms=tuple(ingest_forms))

        row = sess.execute(sqltext("""
            SELECT id, cik, ticker, form, filing_date, accession, source_url, filename
            FROM filings_main
            WHERE ticker = :t
              AND (:f IS NULL OR form = :f)
            ORDER BY filing_date DESC
            LIMIT 1
        """), {"t": tick, "f": form}).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="No main filing found after ingest")
        return dict(row)
    finally:
        sess.close()

# ---------- insights for sections_main ----------
@app.get("/sections/main/{sid}/insights")
def insights_main(sid: int):
    sess = Session()
    try:
        exists = sess.execute(sqltext("SELECT 1 FROM sections_main WHERE id = :sid"), {"sid": sid}).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="Section not found in sections_main")

        risks = sess.execute(sqltext("""
          SELECT label, MAX(score) AS top_score, COUNT(*) AS hits
          FROM classifications
          WHERE section_id = :sid
          GROUP BY label
          ORDER BY top_score DESC
          LIMIT 50
        """), {"sid": sid}).mappings().all()

        sent = sess.execute(sqltext("""
          SELECT label, score
          FROM sentiments
          WHERE section_id = :sid
        """), {"sid": sid}).mappings().first()

        # return {"sentiment": dict(sent) if sent else None,
        #         "risks": [dict(r) for r in risks]}
        sentiment_obj = dict(sent) if sent else {}     # {} not None
        risks_list    = [dict(r) for r in risks] if risks else []  # [] not None

        return {"sentiment": sentiment_obj, "risks": risks_list}
    finally:
        sess.close()
