# from prefect import flow, task
# from src.db import init_db
# from src.edgar.ingest import ingest_one
# from src.nlp.pipelines import analyze_batch

# @task
# def ingest():
#     ingest_one("320193", "AAPL", limit=1)
#     ingest_one("789019", "MSFT", limit=1)

# @task
# def nlp():
#     analyze_batch(limit=8)

# @flow(log_prints=True)
# def daily_run():
#     init_db()
#     ingest()
#     nlp()

# if __name__ == "__main__":
#     daily_run()


from prefect import flow, task
from src.db import init_db
from src.edgar.ingest import ingest_one
from src.nlp.pipelines import analyze_batch_main

@task
def ingest():
    # Add more tickers/CIKs as needed
    ingest_one("320193", "AAPL", limit=1)
    ingest_one("789019", "MSFT", limit=1)

@task
def nlp():
    analyze_batch_main(limit=12)

@flow(log_prints=True)
def daily_run():
    init_db()
    ingest()
    nlp()

if __name__ == "__main__":
    daily_run()
