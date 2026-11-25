#!/usr/bin/env python3
"""Find recently published papers that are not yet on publications.html.

Sources (free, no API keys):
  * OpenAlex  - author A5075797962 (Joachim Moortgat, linked to ORCID)
  * Crossref  - works that carry ORCID 0000-0002-0259-3597 (usually listed
                on the day of publication, before OpenAlex indexes them)

Only journal articles and conference papers count. Preprints, conference
abstracts, datasets and software archives are skipped.

A paper counts as known when its DOI or its title appears on
publications.html, or when its DOI appears in an earlier alert issue
(open or closed). Closing an alert issue therefore also dismisses it.

Usage:
  python3 tools/check_new_papers.py                   # print new papers
  python3 tools/check_new_papers.py --out alert.md    # also write an issue body
  python3 tools/check_new_papers.py --page OLD.html   # test against another page
Exit code is 0 either way; the alert file is only written when something is new.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

OPENALEX_AUTHOR = "A5075797962"
ORCID = "0000-0002-0259-3597"
LABEL = "new-paper"
UA = "publication-checker/1.0 (+https://github.com/jmoortgat/jmoortgat.github.io)"

# DOI prefixes and venues that are never journal or conference papers.
SKIP_DOI = ("10.5281/", "10.48550/", "10.2139/", "10.1002/essoar", "10.22541/essoar",
            "10.5194/egusphere", "10.31223/", "10.1101/", "10.31219/")
SKIP_VENUE = re.compile(r"abstract|fall meeting|general assembly|arxiv|ssrn|zenodo|"
                        r"open archive|eartharxiv|research square|preprint", re.I)


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(re.sub(r"<[^>]+>", "", s or "")))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def from_openalex(since):
    url = ("https://api.openalex.org/works?per_page=100&sort=publication_date:desc&filter="
           + urllib.parse.quote(f"author.id:{OPENALEX_AUTHOR},from_publication_date:{since}"))
    out = []
    for w in get_json(url).get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {})
        if w.get("type") not in ("article", "review", "letter", "book-chapter"):
            continue
        if src.get("type") not in ("journal", "conference", "book series", None):
            continue
        out.append({
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "title": w.get("display_name") or "",
            "venue": src.get("display_name") or "",
            "date": w.get("publication_date") or "",
            "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
            "source": "OpenAlex",
        })
    return out


def from_crossref(since):
    flt = f"orcid:{ORCID},from-pub-date:{since},type:journal-article,type:proceedings-article"
    url = "https://api.crossref.org/works?rows=100&filter=" + urllib.parse.quote(flt, safe=":,")
    out = []
    for m in get_json(url)["message"]["items"]:
        d = (m.get("published-online") or m.get("published-print") or m.get("issued") or {}).get("date-parts", [[None]])[0]
        out.append({
            "doi": m.get("DOI", ""),
            "title": (m.get("title") or [""])[0],
            "venue": (m.get("container-title") or [""])[0],
            "date": "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(d) if x),
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in m.get("author", [])],
            "source": "Crossref",
        })
    return out


def alerted_dois(repo, token):
    """DOIs mentioned in earlier alert issues (open or closed)."""
    if not (repo and token):
        return set()
    url = f"https://api.github.com/repos/{repo}/issues?state=all&labels={LABEL}&per_page=100"
    issues = get_json(url, {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    found = set()
    for i in issues:
        found |= {d.lower() for d in re.findall(r"10\.\d{4,9}/[^\s)\]>`]+", i.get("body") or "")}
    return found


def main():
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--page", default=os.path.join(root, "publications.html"))
    ap.add_argument("--days", type=int, default=180, help="look back this many days")
    ap.add_argument("--out", help="write a GitHub issue body here when there are new papers")
    args = ap.parse_args()

    page = open(args.page, encoding="utf-8").read()
    page_dois = {d.lower() for d in re.findall(r"doi\.org/([^\"<\s]+)", page)}
    page_text = norm(page)
    seen = alerted_dois(os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN"))

    since = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    found, errors = {}, []
    for fetch in (from_crossref, from_openalex):
        try:
            for p in fetch(since):
                key = p["doi"].lower() or norm(p["title"])
                found.setdefault(key, p)
        except Exception as e:  # one source down should not hide the other
            errors.append(f"{fetch.__name__}: {e}")

    new = []
    for key, p in found.items():
        doi = p["doi"].lower()
        if doi.startswith(SKIP_DOI) or SKIP_VENUE.search(p["venue"] or ""):
            continue
        if doi in page_dois or doi in seen:
            continue
        if norm(p["title"])[:40] and norm(p["title"])[:40] in page_text:
            continue
        new.append(p)
    new.sort(key=lambda p: p["date"], reverse=True)

    for e in errors:
        print("warning:", e, file=sys.stderr)
    if not new:
        print(f"No new papers since {since} ({len(found)} works checked).")
        return 0

    lines = []
    for p in new:
        authors = ", ".join(p["authors"][:8]) + (", et al." if len(p["authors"]) > 8 else "")
        lines.append(f"- **{clean(p['title'])}**  \n  {authors}  \n  *{clean(p['venue'])}*, {p['date']}  \n"
                     f"  https://doi.org/{p['doi']}  (found via {p['source']})")
        print(f"NEW  {p['date']}  {p['doi']}  {clean(p['title'])[:80]}")
    if args.out:
        body = ("@jmoortgat these papers were published recently but are not on "
                "[publications.html](https://jmoortgat.github.io/publications.html) yet:\n\n"
                + "\n".join(lines)
                + "\n\nTo add one: put it on `publications.html` with its DOI, then run "
                  "`python3 tools/build_pub_links.py` for the PDF and citation links. "
                  "Close this issue when done. Closing it also dismisses papers you do not want to list; "
                  "they will not be reported again.\n")
        if errors:
            body += "\n<sub>Warnings: " + "; ".join(errors) + "</sub>\n"
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
