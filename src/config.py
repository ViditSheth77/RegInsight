import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/reginsight")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Vidit Sheth viditsheth74@gmail.com")

# Limits
MAX_SECTION_CHARS = 500_000
MAX_DOC_CHARS = 2_000_000

# Models
SUMMARIZER_MODEL = "facebook/bart-large-cnn"
ZEROSHOT_MODEL   = "facebook/bart-large-mnli"
NER_MODEL        = "dslim/bert-base-NER"                # reserved for later use
QA_MODEL         = "deepset/roberta-base-squad2"
FIN_SENT_MODEL   = "ProsusAI/finbert"
EMBED_MODEL      = "sentence-transformers/all-MiniLM-L6-v2"  # reserved for later use
