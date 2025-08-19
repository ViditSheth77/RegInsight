import logging
from transformers import pipeline
from sqlalchemy import text as sqltext
from src.db import Session
from src.utils.text import nontrivial_paragraphs
from src.config import (
  SUMMARIZER_MODEL, ZEROSHOT_MODEL, QA_MODEL, FIN_SENT_MODEL
)
from src.nlp.risk_labels import RISK_LABELS, KPI_QUESTIONS
from src.logging_conf import setup_logging

setup_logging()
logger = logging.getLogger("nlp")

# Load models once
summarizer = pipeline("summarization", model=SUMMARIZER_MODEL)
zeroshot   = pipeline("zero-shot-classification", model=ZEROSHOT_MODEL)
qa         = pipeline("question-answering", model=QA_MODEL)
finbert    = pipeline("sentiment-analysis", model=FIN_SENT_MODEL)

def analyze_batch(limit=8):
    sess = Session()
    try:
        rows = sess.execute(sqltext("""
          SELECT s.id, s.text, s.name, s.filing_id
          FROM sections s
          LEFT JOIN sentiments t ON t.section_id = s.id
          WHERE t.id IS NULL
          ORDER BY s.id DESC
          LIMIT :lim
        """), dict(lim=limit)).mappings().all()

        for r in rows:
            sid, stext, sname, fid = r["id"], r["text"], r["name"], r["filing_id"]

            # Sentiment
            try:
                senti = finbert(stext[:2800])[0]
                sess.execute(sqltext(
                    "INSERT INTO sentiments(section_id,label,score) VALUES(:sid,:lab,:sc)"
                ), dict(sid=sid, lab=senti["label"], sc=float(senti["score"])))
            except Exception as e:
                logger.warning("Sentiment failed for section %s: %s", sid, e)

            # Zero-shot risk tags (per paragraph)
            for i, p in enumerate(nontrivial_paragraphs(stext)[:100]):
                try:
                    zs = zeroshot(p, RISK_LABELS, multi_label=True)
                    for lab, sc in zip(zs["labels"], zs["scores"]):
                        if sc >= 0.55:
                            sess.execute(sqltext("""
                              INSERT INTO classifications(section_id, paragraph_idx, label, score)
                              VALUES(:sid,:pi,:lab,:sc)
                            """), dict(sid=sid, pi=i, lab=lab, sc=float(sc)))
                except Exception as e:
                    logger.debug("ZSL skip p%s sec%s: %s", i, sid, e)

            # KPI QA
            for name, question in KPI_QUESTIONS.items():
                try:
                    ans = qa(question=question, context=stext[:12000])
                    if ans.get("score",0) > 0.2 and ans.get("answer","").strip():
                        start = ans.get("start", 0) or 0
                        end   = ans.get("end", 0) or 0
                        snippet = stext[max(start-60,0): end+60][:400]
                        sess.execute(sqltext("""
                          INSERT INTO kpis (filing_id, name, value, evidence_snippet)
                          VALUES(:fid,:name,:val,:snip)
                        """), dict(fid=fid, name=name, val=ans["answer"][:120], snip=snippet))
                except Exception:
                    pass

        sess.commit()
    finally:
        sess.close()

if __name__ == "__main__":
    analyze_batch()