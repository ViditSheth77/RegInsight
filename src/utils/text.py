def chunk_words(text: str, max_words=1200):
    words, cur, out = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out

def nontrivial_paragraphs(text: str, min_words=7):
    return [p for p in (t.strip() for t in text.split("\n")) if len(p.split()) >= min_words]
