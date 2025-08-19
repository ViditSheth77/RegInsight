# RegInsight

Monitor SEC filings (10-K/10-Q) and extract risks, sentiment, and KPIs using HuggingFace models.

## Quickstart
1) `make init` (creates venv, installs deps, copies .env)
2) Edit `.env` -> set your real `SEC_USER_AGENT`
3) `make db-up` (optional Docker Postgres)
4) `make db-init`
5) `make ingest` (AAPL/MSFT sample)
6) `make nlp`
7) `make api` (FastAPI at http://localhost:8000)
8) `make ui` (Streamlit at http://localhost:8501)
