#!/usr/bin/env python3
"""Add PDF and citation-download links under every paper on publications.html.

For each paper with a DOI (or a manual entry below) this script:
  1. fetches metadata from Crossref and writes cite/<key>.bib and cite/<key>.ris
     (RIS imports into EndNote, Zotero and Mendeley), plus combined files
     cite/moortgat_publications.bib / .ris;
  2. looks for a freely available PDF (OpenAlex and Semantic Scholar open-access
     locations, arXiv, and the manual list below) and keeps the first URL that
     actually returns a PDF;
  3. rewrites each paper's <div class="pub-meta"> line with DOI, PDF, BibTeX and
     RIS links.

Re-run it after adding papers:  python3 tools/build_pub_links.py
API responses are cached in tools/.cache/ (git-ignored); delete it to refresh.
"""
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "publications.html")
CITE_DIR = os.path.join(ROOT, "cite")
CACHE = os.path.join(ROOT, "tools", ".cache")
UA = "Mozilla/5.0 (compatible; publication-link-builder/1.0)"

# DOIs missing from the page, keyed by paper number.
EXTRA_DOI = {17: "10.1073/pnas.1205338109"}

# Papers whose best record is not a Crossref DOI: full metadata given here.
MANUAL = {
    "10.48550/arXiv.2601.12636": {
        "type": "proceedings-article",
        "authors": [("Chowdhury", "Satyaki Roy"), ("Radhakrishnan", "Aswathnarayan"),
                    ("Hsu", "Hsiao-Jou"), ("Subramoni", "Hari"), ("Moortgat", "Joachim")],
        "title": "From Bands to Depth: Understanding Bathymetry Decisions on Sentinel-2",
        "container": "Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV)",
        "year": "2026", "pages": "2063-2072", "publisher": "IEEE",
        "url": "https://openaccess.thecvf.com/content/WACV2026/html/Chowdhury_From_Bands_to_Depth_Understanding_Bathymetry_Decisions_on_Sentinel-2_WACV_2026_paper.html",
    },
    1: {
        "type": "proceedings-article",
        "authors": [("Moortgat", "Joachim"), ("Kuijpers", "Jan")],
        "title": "Indirect Visibility of Gravitational Waves in Magnetohydrodynamic Plasmas",
        "container": "Proceedings of the 22nd Texas Symposium on Relativistic Astrophysics",
        "year": "2005", "address": "Stanford, CA", "eprint": "gr-qc/0503074",
        "url": "https://arxiv.org/abs/gr-qc/0503074",
    },
}

# PDFs to try before the automatic search (e.g. CVF Open Access, arXiv).
EXTRA_PDF = {
    "10.48550/arXiv.2601.12636": [
        "https://openaccess.thecvf.com/content/WACV2026/papers/Chowdhury_From_Bands_to_Depth_Understanding_Bathymetry_Decisions_on_Sentinel-2_WACV_2026_paper.pdf",
        "https://arxiv.org/pdf/2601.12636"],
    1: ["https://arxiv.org/pdf/gr-qc/0503074"],
}


# ---------------------------------------------------------------- HTTP + cache
def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", name)[:180])


def get_json(url, cache_name, data=None):
    path = _cache_path(cache_name + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": UA, "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                out = None
                break
            if e.code == 429 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    with open(path, "w") as f:
        json.dump(out, f)
    return out


def is_pdf(url):
    """True if the URL serves a PDF (checked once, then cached)."""
    path = _cache_path("pdfcheck_" + url + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    ok = False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
        with urllib.request.urlopen(req, timeout=45) as r:
            head = r.read(1024)
            ctype = r.headers.get("Content-Type", "")
            ok = head.lstrip().startswith(b"%PDF") or ("pdf" in ctype.lower() and b"<html" not in head.lower())
    except Exception:
        ok = False
    with open(path, "w") as f:
        json.dump(ok, f)
    return ok


# ---------------------------------------------------------------- page parsing
ITEM_RE = re.compile(
    r'(<li class="pub-item"[^>]*>\s*<span class="pub-num( review)?">(\d+)</span>\s*'
    r'<div class="pub-content">\s*<cite>(.*?)</cite>)(\s*<div class="pub-meta">.*?</div>)?(\s*</div>\s*</li>)',
    re.S)


def plain(s):
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


# ---------------------------------------------------------------- metadata
def from_crossref(doi):
    msg = get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi),
                   "crossref_" + doi)
    if not msg:
        return None
    m = msg["message"]
    date = (m.get("published-print") or m.get("published-online") or m.get("issued"))["date-parts"][0]
    pages = m.get("page") or m.get("article-number") or ""
    return {
        "type": m.get("type", "journal-article"),
        "authors": [(a.get("family", a.get("name", "")), a.get("given", "")) for a in m.get("author", [])],
        "title": (m.get("title") or [""])[0],
        # book chapters list [series, book title]; the book title is the container
        "container": (m.get("container-title") or [""])[-1 if m.get("type") == "book-chapter" else 0],
        "year": str(date[0]),
        "volume": m.get("volume", ""), "issue": m.get("issue", ""),
        "pages": pages, "publisher": m.get("publisher", ""), "doi": doi,
    }


def clean_title(t, latex):
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    sub = r"$_{\1}$" if latex else r"\1"
    t = re.sub(r"<sub>(.*?)</sub>", sub, t)
    t = re.sub(r"<sup>(.*?)</sup>", r"$^{\1}$" if latex else r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    if latex:
        t = t.replace("&", r"\&").replace("%", r"\%")
    return t


def ascii_slug(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


STOP = {"a", "an", "the", "on", "of", "in", "for", "and", "from", "to", "with", "using"}


def make_key(md, used):
    first = ascii_slug(md["authors"][0][0]) if md["authors"] else "anon"
    words = [ascii_slug(w) for w in plain(md["title"]).split()]
    word = next((w for w in words if w and w not in STOP), "paper")
    key = f"{first}{md['year']}{word}"
    k, n = key, 0
    while k in used:
        n += 1
        k = key + "abcdefghij"[n - 1]
    used.add(k)
    return k


BIBTYPE = {"journal-article": "article", "proceedings-article": "inproceedings",
           "book-chapter": "incollection", "posted-content": "misc"}
RISTYPE = {"journal-article": "JOUR", "proceedings-article": "CONF",
           "book-chapter": "CHAP", "posted-content": "GEN"}


def to_bibtex(key, md):
    btype = BIBTYPE.get(md["type"], "article")
    cont = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}.get(btype, "howpublished")
    f = [("author", " and ".join(f"{fam}, {giv}".strip(", ") for fam, giv in md["authors"])),
         ("title", "{" + clean_title(md["title"], True) + "}"),
         (cont, clean_title(md.get("container", ""), True)),
         ("year", md["year"]), ("volume", md.get("volume", "")), ("number", md.get("issue", "")),
         ("pages", md.get("pages", "").replace("-", "--")), ("publisher", md.get("publisher", "")),
         ("address", md.get("address", "")), ("eprint", md.get("eprint", "")),
         ("archivePrefix", "arXiv" if md.get("eprint") else ""),
         ("doi", md.get("doi", "")), ("url", md.get("url") or (f"https://doi.org/{md['doi']}" if md.get("doi") else ""))]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in f if v)
    return f"@{btype}{{{key},\n{body}\n}}\n"


def to_ris(md):
    lines = [f"TY  - {RISTYPE.get(md['type'], 'JOUR')}"]
    lines += [f"AU  - {fam}, {giv}".rstrip(", ") for fam, giv in md["authors"]]
    lines.append(f"TI  - {clean_title(md['title'], False)}")
    if md.get("container"):
        lines.append(("JO  - " if md["type"] == "journal-article" else "T2  - ") + clean_title(md["container"], False))
    lines.append(f"PY  - {md['year']}")
    for tag, k in (("VL", "volume"), ("IS", "issue"), ("PB", "publisher"), ("CY", "address"), ("DO", "doi")):
        if md.get(k):
            lines.append(f"{tag}  - {md[k]}")
    pages = md.get("pages", "")
    if pages:
        sp, _, ep = pages.partition("-")
        lines.append(f"SP  - {sp}")
        if ep:
            lines.append(f"EP  - {ep}")
    url = md.get("url") or (f"https://doi.org/{md['doi']}" if md.get("doi") else "")
    if url:
        lines.append(f"UR  - {url}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- PDF search
def norm(s):
    s = unicodedata.normalize("NFKD", plain(clean_title(s, False)))  # CO₂ -> CO2
    return re.sub(r"[^a-z0-9]", "", s.lower())


def same_title(a, b):
    """True if the first 40 normalized characters of title a occur in text b."""
    a, b = norm(a), norm(b)
    return bool(a) and a[:40] in b


def arxiv_title(arxiv_id):
    path = _cache_path("arxiv_" + arxiv_id + ".txt")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read()
    url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=45) as r:
            xml = r.read().decode("utf-8", "replace")
        titles = re.findall(r"<entry>.*?<title>(.*?)</title>", xml, re.S)
        t = re.sub(r"\s+", " ", titles[0]).strip() if titles else ""
    except Exception:
        t = ""
    time.sleep(3)  # arXiv API etiquette
    with open(path, "w", encoding="utf-8") as f:
        f.write(t)
    return t


def pdf_matches(url, title):
    """arXiv links are only accepted when the arXiv record has the paper's title."""
    m = re.match(r"https?://arxiv\.org/pdf/(.+?)(?:\.pdf)?$", url)
    if not m:
        return True
    return same_title(arxiv_title(m.group(1)), title) or same_title(title, arxiv_title(m.group(1)))


def pdf_candidates(doi):
    cands = []
    oa = get_json("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi), "openalex_" + doi)
    if oa:
        locs = [oa.get("best_oa_location")] + oa.get("locations", [])
        for l in locs:
            if l and l.get("pdf_url") and l.get("is_oa", True):
                cands.append(l["pdf_url"])
        arx = (oa.get("ids") or {}).get("arxiv")
        if arx:
            cands.append("https://arxiv.org/pdf/" + arx.rsplit("/abs/", 1)[-1])
    s2 = get_json("https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(doi)
                  + "?fields=openAccessPdf,externalIds", "s2_" + doi)
    if s2:
        if (s2.get("openAccessPdf") or {}).get("url"):
            cands.append(s2["openAccessPdf"]["url"])
        if (s2.get("externalIds") or {}).get("ArXiv"):
            cands.append("https://arxiv.org/pdf/" + s2["externalIds"]["ArXiv"])
        time.sleep(1.1)  # Semantic Scholar's unauthenticated rate limit
    seen, out = set(), []
    for c in cands:
        c = c.replace("http://", "https://", 1) if c.startswith("http://arxiv") else c
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ---------------------------------------------------------------- main
def main():
    page = open(PAGE, encoding="utf-8").read()
    os.makedirs(CITE_DIR, exist_ok=True)
    used, all_bib, all_ris, report = set(), [], [], []

    def rebuild(m):
        head, review, num, cite, meta, tail = m.groups()
        num = int(num)
        if review:
            return m.group(0)
        old = re.search(r'doi\.org/([^"]+)"', meta or "")
        doi = old.group(1) if old else EXTRA_DOI.get(num)
        md = None
        if doi and doi in MANUAL:
            md = dict(MANUAL[doi], doi=doi)
        elif num in MANUAL and not doi:
            md = dict(MANUAL[num])
        elif doi:
            md = from_crossref(doi)
        if not md:
            report.append((num, "NO METADATA", ""))
            return m.group(0)
        if not same_title(md["title"], cite):
            report.append((num, "TITLE MISMATCH: " + plain(md["title"])[:60], ""))
            return m.group(0)
        if not md.get("year") or md["year"] == "None":
            y = re.search(r"\((\d{4})\)", plain(cite))
            md["year"] = y.group(1) if y else ""
        key = make_key(md, used)
        bib, ris = to_bibtex(key, md), to_ris(md)
        with open(os.path.join(CITE_DIR, key + ".bib"), "w", encoding="utf-8") as f:
            f.write(bib)
        with open(os.path.join(CITE_DIR, key + ".ris"), "w", encoding="utf-8") as f:
            f.write(ris)
        all_bib.append(bib)
        all_ris.append(ris)

        pdf = None
        for url in EXTRA_PDF.get(doi, []) + EXTRA_PDF.get(num, []) + (pdf_candidates(doi) if doi else []):
            if pdf_matches(url, md["title"]) and is_pdf(url):
                pdf = url
                break
        report.append((num, key, pdf or ""))

        links = []
        if doi:
            links.append(f'<a href="https://doi.org/{doi}" target="_blank" rel="noopener">doi:{doi}</a>')
        elif md.get("url"):
            links.append(f'<a href="{md["url"]}" target="_blank" rel="noopener">arXiv:{md.get("eprint", "")}</a>')
        if pdf:
            links.append(f'<a class="pub-link pub-link-pdf" href="{html.escape(pdf)}" target="_blank" rel="noopener">PDF</a>')
        links.append(f'<a class="pub-link" href="cite/{key}.bib" download title="BibTeX (LaTeX)">BibTeX</a>')
        links.append(f'<a class="pub-link" href="cite/{key}.ris" download title="RIS: imports into EndNote, Zotero and Mendeley">EndNote / RIS</a>')
        meta_html = '\n              <div class="pub-meta">' + " ".join(links) + "</div>"
        return head + meta_html + tail

    page = ITEM_RE.sub(rebuild, page)
    with open(os.path.join(CITE_DIR, "moortgat_publications.bib"), "w", encoding="utf-8") as f:
        f.write("\n".join(all_bib))
    with open(os.path.join(CITE_DIR, "moortgat_publications.ris"), "w", encoding="utf-8") as f:
        f.write("\n".join(all_ris))
    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(page)

    n_pdf = sum(1 for r in report if r[2])
    for num, key, pdf in sorted(report, reverse=True):
        print(f"{num:>3}  {key:<32} {pdf or '-'}")
    print(f"\n{len(report)} papers, {n_pdf} with a verified PDF link.")


if __name__ == "__main__":
    sys.exit(main())
