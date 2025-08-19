import streamlit as st
import requests

API = "http://localhost:8000"

st.set_page_config(page_title="RegInsight", layout="wide")
st.title("RegInsight — SEC Filing Monitor")

# ----------------------------
# Controls
# ----------------------------
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    ident = st.text_input(
        "Ticker (e.g., AAPL, NVDA, TSLA) or CIK",
        "AAPL",
        help="Enter a stock ticker or a numeric CIK."
    ).strip().upper()
with c2:
    form = st.selectbox("Form", ["Any", "10-Q", "10-K", "8-K", "20-F", "6-K"], index=0)
with c3:
    limit = st.number_input("How many recent filings?", min_value=1, max_value=20, value=5, step=1)

# ----------------------------
# Helpers
# ----------------------------
def fetch_json(url: str, params: dict | None = None, method: str = "GET", timeout: int = 45):
    try:
        if method.upper() == "POST":
            r = requests.post(url, params=params, timeout=timeout)
        else:
            r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"{method} {url} failed: {e}")
        return None

def load_filings(identifier: str, form_choice: str, limit_val: int):
    """Call /filings/main with auto_ingest=True; return rows or []"""
    params = {
        "identifier": identifier,
        "limit": limit_val,
        "auto_ingest": True
    }
    if form_choice != "Any":
        params["form"] = form_choice

    return fetch_json(f"{API}/filings/main", params=params) or []

# ----------------------------
# Load button
# ----------------------------
if st.button("Load Filings"):
    rows = load_filings(ident, form, limit)
    st.session_state["rows"] = rows

rows = st.session_state.get("rows", [])

# ----------------------------
# Render
# ----------------------------
if not rows:
    st.info("No filings loaded yet. Enter a ticker/CIK and click **Load Filings**.")
else:
    for f in rows:
        header = f"{f.get('ticker','?')} {f.get('form','?')} • {f.get('filing_date','?')}"
        with st.expander(header, expanded=False):
            fid = f.get("id")
            if fid is None:
                st.warning("This entry has no filing ID; skipping.")
                continue

            # Fetch main filing details + sections
            fr = fetch_json(f"{API}/filings/main/{fid}")
            if not fr:
                st.warning(f"Could not load filing details for id={fid}.")
                continue

            filing = fr.get("filing", {}) or {}
            sections = fr.get("sections", []) or []

            m1, m2, m3 = st.columns(3)
            with m1:
                st.caption("Accession / Filename")
                st.code(filing.get("filename", "—"))
            with m2:
                st.caption("Source URL")
                url = filing.get("source_url", "")
                if url:
                    st.write(url)
                else:
                    st.write("—")
            with m3:
                st.caption("CIK")
                st.code(filing.get("cik", "—"))

            if not sections:
                st.write("No sections found for this filing yet.")
                continue

            for s in sections:
                st.subheader(s.get("name", "Section"))
                st.write((s.get("preview", "") or "")[:1500] + "…")

                sid = s.get("id")
                if sid is None:
                    st.caption("No section ID; skipping insights.")
                    continue

                ir = fetch_json(f"{API}/sections/main/{s['id']}/insights") or {}
                cL, cR = st.columns(2)
                with cL:
                    st.caption("Sentiment")
                    st.json(ir.get("sentiment"))
                with cR:
                    st.caption("Top Risk Tags")
                    risks = ir.get("risks", [])
                    if risks:
                        st.table(risks[:8])
                    else:
                        st.write("—")
