import logging
from sqlalchemy import create_engine, text as sqltext
from sqlalchemy.orm import sessionmaker
from src.config import DATABASE_URL
from src.logging_conf import setup_logging

setup_logging()
logger = logging.getLogger("db")

engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Legacy tables (kept for compatibility)
DDL_LEGACY = """
CREATE TABLE IF NOT EXISTS filings (
  id SERIAL PRIMARY KEY,
  cik VARCHAR(20),
  ticker VARCHAR(16),
  form VARCHAR(10),
  filing_date DATE,
  source_url TEXT,
  raw_text TEXT
);
CREATE TABLE IF NOT EXISTS sections (
  id SERIAL PRIMARY KEY,
  filing_id INT REFERENCES filings(id) ON DELETE CASCADE,
  name TEXT,
  text TEXT
);
CREATE TABLE IF NOT EXISTS classifications (
  id SERIAL PRIMARY KEY,
  section_id INT REFERENCES sections(id) ON DELETE CASCADE,
  paragraph_idx INT,
  label TEXT,
  score FLOAT
);
CREATE TABLE IF NOT EXISTS sentiments (
  id SERIAL PRIMARY KEY,
  section_id INT REFERENCES sections(id) ON DELETE CASCADE,
  label TEXT,
  score FLOAT
);
CREATE TABLE IF NOT EXISTS kpis (
  id SERIAL PRIMARY KEY,
  filing_id INT REFERENCES filings(id) ON DELETE CASCADE,
  name TEXT,
  value TEXT,
  evidence_snippet TEXT
);
"""

def init_db():
    with engine.begin() as conn:
        # New main/exhibit schema
        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS filings_main (
          id BIGSERIAL PRIMARY KEY,
          cik TEXT NOT NULL,
          ticker TEXT,
          form TEXT,
          filing_date DATE,
          accession TEXT UNIQUE,
          source_url TEXT,
          filename TEXT,
          raw_text TEXT
        );"""))

        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS sections_main (
          id BIGSERIAL PRIMARY KEY,
          filing_id BIGINT REFERENCES filings_main(id) ON DELETE CASCADE,
          name TEXT,
          text TEXT
        );"""))

        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS filings_exhibits (
          id BIGSERIAL PRIMARY KEY,
          filing_accession TEXT,
          cik TEXT NOT NULL,
          ticker TEXT,
          form TEXT,
          filing_date DATE,
          filename TEXT,
          url TEXT,
          doc_type TEXT,
          description TEXT,
          size INTEGER,
          text TEXT
        );"""))

        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS kpis_main (
          id BIGSERIAL PRIMARY KEY,
          filing_id BIGINT REFERENCES filings_main(id) ON DELETE CASCADE,
          name TEXT,
          value TEXT,
          evidence_snippet TEXT
        );"""))
        # --- NEW: NLP outputs keyed to sections_main -remove if not needed--
        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS sentiments_main (
          id          BIGSERIAL PRIMARY KEY,
          section_id  BIGINT REFERENCES sections_main(id) ON DELETE CASCADE,
          label       TEXT,
          score       FLOAT
        );
        """))

        conn.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS classifications_main (
          id            BIGSERIAL PRIMARY KEY,
          section_id    BIGINT REFERENCES sections_main(id) ON DELETE CASCADE,
          paragraph_idx INT,
          label         TEXT,
          score         FLOAT
        );
        """))

        # Unique per label per paragraph (prevents duplicates)
        conn.execute(sqltext("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_class_main_sec_para_label
          ON classifications_main (section_id, paragraph_idx, label);
        """))

        # Helpful indexes
        conn.execute(sqltext("""
        CREATE INDEX IF NOT EXISTS idx_sentiments_main_section
          ON sentiments_main (section_id);
        """))
        conn.execute(sqltext("""
        CREATE INDEX IF NOT EXISTS idx_classifications_main_section
          ON classifications_main (section_id);
        """))

        # Helpful indexes
        conn.execute(sqltext("CREATE INDEX IF NOT EXISTS idx_filings_main_cik_date ON filings_main (cik, filing_date DESC);"))
        conn.execute(sqltext("CREATE INDEX IF NOT EXISTS idx_sections_main_filing_id ON sections_main (filing_id);"))
        conn.execute(sqltext("CREATE INDEX IF NOT EXISTS idx_exhibits_accession ON filings_exhibits (filing_accession);"))

        # Legacy tables (optional, retained)
        for stmt in DDL_LEGACY.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(sqltext(s))

        # Unique classification key to avoid dup labels per paragraph (safe if no dups present)
        try:
            conn.execute(sqltext("""
              CREATE UNIQUE INDEX IF NOT EXISTS uniq_class_per_para
              ON classifications (section_id, paragraph_idx, label);
            """))
        except Exception as e:
            # If duplicates exist, pipeline upserts will prevent new dups; you can clean old ones manually.
            logger.warning("Could not create uniq_class_per_para index (likely duplicates exist): %s", e)

    logger.info("DB initialized.")

if __name__ == "__main__":
    init_db()
