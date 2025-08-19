init:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cp -n .env.example .env || true

db-up:
	docker compose up -d db adminer

db-init:
	. .venv/bin/activate && python -m src.db

INGEST_FORMS ?= 10-K,10-Q

ingest-aapl:
	. .venv/bin/activate && python -m src.edgar.ingest --cik 320193 --ticker AAPL --limit 2 --forms "$(INGEST_FORMS)"

ingest-msft:
	. .venv/bin/activate && python -m src.edgar.ingest --cik 789019 --ticker MSFT --limit 2 --forms "$(INGEST_FORMS)"


ingest:
	. .venv/bin/activate && python -m src.edgar.ingest \
		--cik $(CIK) \
		--ticker $(TICKER) \
		--limit $(LIMIT) \
		--forms "$(INGEST_FORMS)"

nlp:
	. .venv/bin/activate && python -m src.nlp.pipelines

api:
	. .venv/bin/activate && uvicorn src.api.app:app --reload --port 8000

ui:
	. .venv/bin/activate && streamlit run src/ui/dashboard.py

flow:
	. .venv/bin/activate && python -m src.flow.daily
