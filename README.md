# RegInsight — AI Risk & KPI Monitor for SEC Filings

**Repo:** https://github.com/ViditSheth77/RegInsight

RegInsight ingests U.S. SEC filings (e.g., **10-K**, **10-Q**, **8-K**), parses them into sections, and stores structured insights in a PostgreSQL database. It includes utilities to summarize filings, classify risks, extract KPIs, and serve results via API/UI—reducing analyst review time from hours to minutes.

---

## Why this project?

Public-company filings are long and frequent. Analysts need **risk changes**, **KPI deltas**, and **tone** quickly. RegInsight automates:

- **Ingestion** of the latest filings for selected tickers/CIKs  
- **Sectioning & cleaning** (e.g., MD&A, Risk Factors)  
- **Classification** (zero-shot risk tags per paragraph)  
- **Sentiment** (e.g., FinBERT for MD&A/Risk Factors)  
- **KPI extraction** (QA queries and rules)  
- **Storage** in PostgreSQL for dashboards and APIs

---

## Key Features

- **EDGAR ingestion** of canonical main filing documents (iXBRL/HTML)
- **Robust parsing** with BeautifulSoup/trafilatura → clean text
- **Structured storage** in Postgres:
  - `filings_main` (one row per main filing)
  - `sections_main` (one row per section)
  - `classifications` (risk tags per paragraph, unique on `(section_id, paragraph_idx, label)`)
- **Re-ingestion safety** via upserts (no duplicate accession crashes)
- **FastAPI endpoints** for filings/sections/insights
- **Streamlit UI** for browsing filings & top risks

---

## Prerequisites

- **Python** 3.11+
- **PostgreSQL** 13+ (Docker recommended)
- **Git**
- (Optional) **Docker Compose**, **Adminer** for quick DB inspection
- (Optional) **Alembic** for DB migrations

---

## Installation

```bash
git clone https://github.com/ViditSheth77/RegInsight.git
cd RegInsight

# Create/activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Quick Postgres via Docker

```yaml
# docker-compose.yml (excerpt)
services:
  db:
    image: postgres:latest
    environment:
      POSTGRES_USER: reginsight_user
      POSTGRES_PASSWORD: password123
      POSTGRES_DB: reginsight
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  adminer:
    image: adminer:latest
    ports:
      - "8080:8080"
volumes:
  postgres_data:
```

Run it:

```bash
docker compose up -d
```

Set your DB URL:

```bash
export DATABASE_URL="postgresql://reginsight_user:password123@localhost:5432/reginsight"
```

Initialize the schema:

```bash
# Either:
python -m src.db

# Or, if you have a Makefile:
make db-init
```

---

## Usage

### Ingest filings (AAPL, MSFT examples)

```bash
# Single command
python -m src.edgar.ingest --cik 320193 --ticker AAPL --limit 1 --forms "10-Q,10-K"

python -m src.edgar.ingest --cik 789019 --ticker MSFT --limit 1 --forms "10-K"
```

If you have Make targets:

```bash
# With variables
make ingest CIK=320193 TICKER=AAPL LIMIT=1 INGEST_FORMS="10-Q,10-K"
make ingest CIK=789019 TICKER=MSFT LIMIT=1 INGEST_FORMS="10-K"
```

### Run NLP (summaries/tags/sentiment/KPI extraction)

```bash
make nlp
# or
python -m src.nlp.pipelines
```

### Start API

```bash
uvicorn src.api.app:app --reload --port 8000
```

- `GET /filings/main?identifier=AAPL&limit=5`
- `GET /filings/main/{id}`
- `GET /sections/main/{section_id}/insights`

### Start UI

```bash
streamlit run src/ui/dashboard.py
```

---

## Code Structure

```
RegInsight/
├─ src/
│  ├─ api/
│  │  └─ app.py               # FastAPI endpoints for filings/sections/insights
│  ├─ db.py                   # DB engine, session, CREATE TABLEs
│  ├─ edgar/
│  │  ├─ ingest.py            # Ingestion: EDGAR index → main doc → text → DB
│  │  ├─ client.py            # HTTP client helper (User-Agent, retries)
│  │  ├─ parsing.py           # HTML→text, section splitting
│  │  └─ secmap.py            # Ticker↔CIK resolver
│  ├─ nlp/
│  │  ├─ pipelines.py         # Summarizer, ZS risk classify, QA, sentiment
│  │  └─ risk_labels.py       # Risk taxonomy & KPI questions
│  ├─ ui/
│  │  └─ dashboard.py         # Streamlit analyst UI
│  └─ utils/
│     └─ text.py              # paragraph helpers, cleaning
├─ requirements.txt
├─ docker-compose.yml
└─ README.md  (this file)
```

---

## Database Schema (core tables)

- **`filings_main`**: canonical main filing (iXBRL/HTML), one per accession  
  Columns: `id`, `cik`, `ticker`, `form`, `filing_date`, `accession` (UNIQUE), `source_url`, `filename`, `raw_text`

- **`sections_main`**: sections extracted from a main filing  
  Columns: `id`, `filing_id` (FK → `filings_main.id`), `name`, `text`

- **`classifications`**: paragraph-level risk tags  
  Columns: `id`, `section_id` (FK), `paragraph_idx`, `label`, `score`  
  Constraint: `UNIQUE (section_id, paragraph_idx, label)`

> If you later adopt dedicated NLP tables (e.g., `sentiments_main`, `classifications_main`), update the API/NLP paths accordingly.

---

## 📸 Demo Screenshot
SEC Filing Monitor report for MICROSOFT (MSFT) of 2025-07-30:
<img width="1512" height="782" alt="image" src="https://github.com/user-attachments/assets/36dc38e3-680f-4824-903b-9b310dfe7fc8" />
SEC Filing Monitor report for MICROSOFT (MSFT) of 2025-04-30
<img width="1508" height="736" alt="image" src="https://github.com/user-attachments/assets/3f87cd95-7e76-4532-914b-0c00cc29b52e" />


SEC Filing Monitor report for Apple (AAPL):
<img width="1511" height="808" alt="image" src="https://github.com/user-attachments/assets/f475ceff-42e7-47a9-8252-803264f970bd" />
<img width="1504" height="807" alt="image" src="https://github.com/user-attachments/assets/de570d5c-2871-4b22-96b1-19c453333404" />





## Troubleshooting

### 1. Password Authentication Failed
Check `DATABASE_URL` credentials.

### 2. Missing Tables
Run:
```bash
python -m src.db
```

### 3. Duplicate Accession
Handled by `ON CONFLICT` upserts.

### 4. Unique Constraint Failures
De-dupe rows, then add the constraint.

### 5. lxml Clean ImportError
```bash
pip install "lxml[html_clean]"
```

### 6. Wrong Document Picked
Check `pick_main_document` logic in `ingest.py`.

### 7. 404 on `/filings/main/{id}`
Verify row exists in DB.

---

## Contributing

1. Fork repo
2. Create feature branch
3. Commit & push
4. Open PR

---

## License

This project is licensed under the **MIT License**.  
See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- SEC EDGAR for filings
- Hugging Face Transformers for NLP
- Streamlit & FastAPI for rapid productization
