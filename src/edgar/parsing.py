from bs4 import BeautifulSoup
import trafilatura

def extract_main_html(html_index: str) -> str | None:
    soup = BeautifulSoup(html_index, "html.parser")
    # Prefer main 10-K/10-Q HTML
    for a in soup.select("a[href]"):
        href = a["href"].lower()
        if href.endswith((".htm", ".html")) and ("10-k" in href or "10-q" in href or "form10" in href):
            return a["href"]
    a = soup.select_one("a[href$='.htm'], a[href$='.html']")
    return a["href"] if a else None

def html_to_text(html: str) -> str:
    txt = trafilatura.extract(html, include_tables=True, include_formatting=False)
    if txt:
        return txt
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")

def split_sections(full_text: str):
    title_map = [
        ("RISK FACTORS", "Risk Factors"),
        ("MANAGEMENT’S DISCUSSION", "MD&A"),
        ("MANAGEMENT'S DISCUSSION", "MD&A"),
        ("QUANTITATIVE AND QUALITATIVE", "Market Risk"),
    ]
    out, idxs, up = [], [], full_text.upper()
    for key, name in title_map:
        i = up.find(key)
        if i != -1: idxs.append((i, name))
    idxs.sort()
    for i,(start,name) in enumerate(idxs):
        end = idxs[i+1][0] if i+1 < len(idxs) else len(full_text)
        out.append((name, full_text[start:end].strip()))
    return out or [("Document", full_text)]
