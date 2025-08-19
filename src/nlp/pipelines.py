import logging, torch
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForSequenceClassification, AutoModelForQuestionAnswering
from sqlalchemy import text as sqltext
from src.db import Session
from src.utils.text import nontrivial_paragraphs
from src.config import SUMMARIZER_MODEL, ZEROSHOT_MODEL, QA_MODEL, FIN_SENT_MODEL
from src.nlp.risk_labels import RISK_LABELS, KPI_QUESTIONS
from src.logging_conf import setup_logging

setup_logging()
logger = logging.getLogger("nlp")

def _pick_device():
    if torch.cuda.is_available(): return 0
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available(): return "mps"
    return -1
DEVICE = _pick_device()

# models
_sum_tok = AutoTokenizer.from_pretrained(SUMMARIZER_MODEL)
_sum_mod = AutoModelForSeq2SeqLM.from_pretrained(SUMMARIZER_MODEL)
summarizer = pipeline("summarization", model=_sum_mod, tokenizer=_sum_tok, device=DEVICE)

_zs_tok = AutoTokenizer.from_pretrained(ZEROSHOT_MODEL)
_zs_mod = AutoModelForSequenceClassification.from_pretrained(ZEROSHOT_MODEL)
zeroshot = pipeline("zero-shot-classification", model=_zs_mod, tokenizer=_zs_tok, device=DEVICE)

_qa_tok = AutoTokenizer.from_pretrained(QA_MODEL)
_qa_mod = AutoModelForQuestionAnswering.from_pretrained(QA_MODEL)
qa = pipeline("question-answering", model=_qa_mod, tokenizer=_qa_tok, device=DEVICE)

_fin_tok = AutoTokenizer.from_pretrained(FIN_SENT_MODEL)
_fin_mod = AutoModelForSequenceClassification.from_pretrained(FIN_SENT_MODEL)
finbert = pipeline("sentiment-analysis", model=_fin_mod, tokenizer=_fin_tok, device=DEVICE)

FIN_MAXLEN = _fin_tok.model_max_length or 512
ZS_MAXLEN  = _zs_tok.model_max_length  or 512
QA_MAXLEN  = _qa_tok.model_max_length  or 512

def analyze_batch(limit=8):
    sess = Session()
    try:
        rows = sess.execute(sqltext("""
          SELECT s.id, s.text, s.name, s.filing_id
          FROM sections_main s
          LEFT JOIN sentiments_main t ON t.section_id = s.id
          WHERE t.id IS NULL
          ORDER BY s.id DESC
          LIMIT :lim
        """), dict(lim=limit)).mappings().all()

        for r in rows:
            sid, stext, sname, fid = r["id"], r["text"], r["name"], r["filing_id"]

            # --- Sentiment (truncate to model max tokens) ---
            try:
                senti = finbert(
                    stext,
                    truncation=True,
                    max_length=FIN_MAXLEN
                )[0]
                sess.execute(sqltext(
                    "INSERT INTO sentiments_main(section_id,label,score) VALUES(:sid,:lab,:sc)"
                ), dict(sid=sid, lab=senti["label"], sc=float(senti["score"])))
            except Exception as e:
                logger.warning("Sentiment failed for section %s: %s", sid, e)

            # --- Zero-shot risk tags (cap paragraph length for safety) ---
            for i, p in enumerate(nontrivial_paragraphs(stext)[:100]):
                try:
                    zs = zeroshot(
                        p,
                        RISK_LABELS,
                        multi_label=True,
                        truncation=True,
                        max_length=ZS_MAXLEN
                    )
                    for lab, sc in zip(zs["labels"], zs["scores"]):
                        if sc >= 0.55:
                            # upsert into classifications_main
                            sess.execute(sqltext("""
                              INSERT INTO classifications_main (section_id, paragraph_idx, label, score)
                              VALUES (:sid, :pi, :lab, :sc)
                              ON CONFLICT (section_id, paragraph_idx, label)
                              DO UPDATE SET score = GREATEST(classifications_main.score, EXCLUDED.score);
                            """), dict(sid=sid, pi=i, lab=lab, sc=float(sc)))
                except Exception as e:
                    logger.debug("ZSL skip p%s sec%s: %s", i, sid, e)

            # --- KPI QA (truncate context to avoid > max_length) ---
            for name, question in KPI_QUESTIONS.items():
                try:
                    ans = qa(
                        question=question,
                        context=stext,
                        truncation=True,
                        max_length=QA_MAXLEN
                    )
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
