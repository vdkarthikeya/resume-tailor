"""Fetch a job description from a job link.

Order: Greenhouse / Lever / Ashby public APIs, then JSON-LD JobPosting, then
readable page text. Login-walled sites (LinkedIn, Handshake, Workday...) can't be
fetched, so we say so and the UI falls back to paste.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
WALLED = ("linkedin.com", "handshake", "joinhandshake.com", "myworkdayjobs.com", "workday", "icims.com", "taleo", "indeed.com", "glassdoor.com")


class JDError(Exception):
    pass


def html_to_text(h: str) -> str:
    soup = BeautifulSoup(h or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for t in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "tr"]):
        t.append("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response:
    return client.get(url, headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"}, timeout=20, follow_redirects=True, **kw)


def trim_boilerplate(text: str) -> str:
    """Drop leading menu/nav lines and trailing footer links; keep from the first real paragraph."""
    lines = [l.rstrip() for l in text.splitlines()]
    first = next((i for i, l in enumerate(lines) if len(l.strip()) >= 90), None)
    if first is None:
        return text
    start = first
    heads = 0
    while start > 0 and heads < 3:  # keep up to 3 short heading lines right above (e.g. "Description")
        prev = lines[start - 1].strip()
        if not prev:
            start -= 1
            continue
        if len(prev) < 60 and not prev.startswith("-"):
            start -= 1
            heads += 1
        else:
            break
    body = lines[start:]
    end = len(body)
    for i, l in enumerate(body):
        if re.match(r"^\s*(share this job|similar jobs|about amazon|privacy|cookie|equal opportunity employer\b.{0,3}$)", l, re.I) and i > 3:
            end = i
            break
    out = "\n".join(body[:end])
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def clean_role(title: str, company: str = "") -> str:
    """'Amazon - Software Development Engineer Intern - Summer 2027 (USA) - Job ID: 123 | Amazon.jobs' -> 'Software Development Engineer Intern'"""
    t = (title or "").split("|")[0].strip()
    t = re.sub(r"\bjob\s*(id|#|number|req(uisition)?)\s*[:#]?\s*[\w-]+", "", t, flags=re.I)
    t = re.sub(r"\bR-?\d{4,}\b|\bREQ[-\s]?\d+\b", "", t, flags=re.I)
    t = re.sub(r"[\(\[][^)\]]*[\)\]]", "", t)
    season = r"(summer|fall|winter|spring)"
    t = re.sub(rf"[-–—,:]?\s*\b{season}\s*(20\d\d)?\b(\s*(20\d\d))?", "", t, flags=re.I)
    t = re.sub(r"[-–—,:]?\s*\b20\d\d\b", "", t)
    if company:
        c = re.escape(company.strip())
        t = re.sub(rf"^\s*{c}\s*[-–—:|,]\s*", "", t, flags=re.I)
        t = re.sub(rf"\s*[-–—:|,]?\s*\bat\s+{c}\b.*$", "", t, flags=re.I)
        t = re.sub(rf"\s*[-–—:|,]\s*{c}\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+[-–—]\s+", " - ", t)
    t = re.sub(r"(\s*[-–—:,]\s*)+$", "", t)
    t = re.sub(r"^(\s*[-–—:,]\s*)+", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def guess_company(title: str, soup=None, host: str = "") -> str:
    parts = [p.strip() for p in (title or "").split("|")]
    if len(parts) > 1:
        c = re.sub(r"\.(jobs|com|io|co|careers)$", "", parts[-1], flags=re.I).strip()
        if c and len(c) < 40:
            return c
    if soup is not None:
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            return og["content"].strip()
    labels = [x for x in host.lower().split(".") if x not in ("www", "careers", "jobs", "com", "io", "co", "net", "org", "boards", "apply")]
    return labels[0].capitalize() if labels else ""


_ROLE = re.compile(r"\b(intern(ship)?|engineer(ing)?|developer|scientist|analyst|researcher|research|manager|associate|co-?op|fellow|architect|specialist|designer|programmer)\b", re.I)
_NOT_COMPANY = {"the", "this", "that", "us", "you", "our", "your", "we", "a", "an", "role", "team", "job", "position", "company",
                "opportunity", "internship", "program", "benefits", "overview", "description", "responsibilities", "qualifications", "it", "what", "who"}
_NOISE = re.compile(r"\b(job\s*id|req(uisition)?|remote|hybrid|on-?site|full[- ]time|part[- ]time|apply|posted|summer|fall|winter|spring|20\d\d)\b|\d{4,}", re.I)


def _tidy_company(c: str) -> str:
    c = re.sub(r"[\(\[][^)\]]*[\)\]]", "", c or "")
    c = re.sub(r"\s+", " ", c).strip(" \t-–—|:,.")
    return "" if (not c or len(c) > 40 or c.lower() in _NOT_COMPANY) else c


def _split_headline(line: str):
    """'Machine Learning Intern at Scale AI' / 'Scale AI - ML Intern' / 'ML Intern | Scale AI' -> (title, company) or None."""
    if len(line) > 120 or not _ROLE.search(line):
        return None
    m = re.match(r"^(?P<t>.+?)\s+at\s+(?P<c>[A-Z][^|]{1,40})$", line)
    if m and _ROLE.search(m["t"]):
        return m["t"], _tidy_company(m["c"])
    parts = [p.strip() for p in re.split(r"\s*(?:\||\s[-–—]\s)\s*", line) if p.strip()]
    if len(parts) >= 2:
        role_parts = [p for p in parts if _ROLE.search(p)]
        others = [p for p in parts if not _ROLE.search(p) and not _NOISE.search(p)]
        if role_parts:
            return role_parts[0], _tidy_company(others[0]) if others else ""
    if re.search(r"[.!?]$", line) or len(line.split()) > 12:
        return None  # a sentence, not a title
    return line, ""


def guess_meta(text: str) -> dict:
    """Best-effort company and role from pasted job text, so the tracker fields can fill themselves."""
    lines = [re.sub(r"^[\s#*•\-]+", "", l).strip() for l in (text or "").splitlines()]
    lines = [l for l in lines if l]
    company = title = ""
    for l in lines[:40]:  # "Company: Netflix" / "Job Title: ..." style labels
        m = re.match(r"^(company|employer|organization|organisation)\s*[:\-]\s*(.+)$", l, re.I)
        if m and not company:
            company = _tidy_company(m.group(2))
        m = re.match(r"^(job\s*title|position|role|title)\s*[:\-]\s*(.+)$", l, re.I)
        if m and not title:
            title = m.group(2).strip()
    if not title or not company:
        for i, l in enumerate(lines[:8]):  # headline near the top
            h = _split_headline(l)
            if h:
                title = title or h[0]
                company = company or h[1]
                prev = lines[i - 1] if i > 0 else ""  # LinkedIn style: company on the line above the title
                if not company and prev and len(prev.split()) <= 4 and not _ROLE.search(prev) and not _NOISE.search(prev):
                    company = _tidy_company(prev)
                break
    if not title:
        for l in lines[:25]:  # any short line that reads like a job title
            if len(l) <= 90 and _ROLE.search(l) and not re.search(r"[.!?]$", l) and len(l.split()) <= 12:
                title = l
                break
    if not company:
        pats = [r"^about\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s*$",
                r"\b(?i:join|joining)\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\b(?=\s+(?:as|and|to|in|on|for)\b|[,.!])",
                r"^at\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3}),\s+we\b",
                r"^([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+is\s+(?:a|an|the|hiring|looking|seeking|building|on a mission)\b"]
        for l in lines[:60]:
            for p in pats:
                m = re.search(p, l)
                if m and _tidy_company(m.group(1)):
                    company = _tidy_company(m.group(1))
                    break
            if company:
                break
    return {"title": clean_role(title, company) if title else "", "company": company}


def _result(title, company, text, url, source):
    return {"title": title or "", "company": company or "", "text": text.strip(), "url": url, "source": source}


def from_greenhouse(client, u) -> dict | None:
    host, path = u.netloc.lower(), u.path.strip("/").split("/")
    board = job = None
    if "greenhouse.io" in host:
        qs = parse_qs(u.query)
        if "for" in qs and "token" in qs:
            board, job = qs["for"][0], qs["token"][0]
        elif "jobs" in path:
            i = path.index("jobs")
            board = path[0] if i > 0 else None
            job = path[i + 1] if i + 1 < len(path) else None
        if not board and "gh_jid" in qs:
            return None
    else:
        qs = parse_qs(u.query)
        if "gh_jid" in qs:
            return None  # company-hosted board: handled by generic path
    if not (board and job):
        return None
    r = _get(client, f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job}")
    if r.status_code != 200:
        return None
    d = r.json()
    text = html_to_text(html.unescape(d.get("content", "")))
    return _result(d.get("title"), board, text, u.geturl(), "greenhouse")


def from_lever(client, u) -> dict | None:
    if "lever.co" not in u.netloc.lower():
        return None
    parts = u.path.strip("/").split("/")
    if len(parts) < 2:
        return None
    r = _get(client, f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}")
    if r.status_code != 200:
        return None
    d = r.json()
    chunks = [d.get("descriptionPlain") or html_to_text(d.get("description", ""))]
    for lst in d.get("lists", []):
        chunks.append(lst.get("text", "") + "\n" + html_to_text(lst.get("content", "")))
    chunks.append(d.get("additionalPlain") or "")
    return _result(d.get("text"), parts[0], "\n\n".join(c for c in chunks if c), u.geturl(), "lever")


def from_ashby(client, u) -> dict | None:
    if "ashbyhq.com" not in u.netloc.lower():
        return None
    parts = u.path.strip("/").split("/")
    if len(parts) < 2:
        return None
    org, job = parts[0], parts[1]
    r = _get(client, f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true")
    if r.status_code != 200:
        return None
    for j in r.json().get("jobs", []):
        if j.get("id") == job:
            text = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", ""))
            return _result(j.get("title"), org, text, u.geturl(), "ashby")
    return None


def _jsonld_job(soup) -> dict | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("@graph"):
                    stack.extend(d["@graph"])
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return d
            elif isinstance(d, list):
                stack.extend(d)
    return None


def from_page(client, u) -> dict:
    r = _get(client, u.geturl())
    if r.status_code in (401, 403, 999):
        raise JDError(f"The site blocked automated access (HTTP {r.status_code}). Paste the job description instead.")
    if r.status_code >= 400:
        raise JDError(f"Could not open the link (HTTP {r.status_code}). Paste the job description instead.")
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise JDError("That link is not a web page. Paste the job description instead.")
    soup = BeautifulSoup(r.text, "html.parser")
    job = _jsonld_job(soup)
    if job and job.get("description"):
        org = job.get("hiringOrganization")
        company = org.get("name") if isinstance(org, dict) else (org or "")
        return _result(job.get("title"), company, html_to_text(html.unescape(job["description"])), u.geturl(), "json-ld")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript", "svg", "form"]):
        t.decompose()
    node = soup.find("main") or soup.find("article") or soup.body or soup
    text = html_to_text(str(node))
    raw_title = soup.title.get_text(strip=True) if soup.title else ""
    company = guess_company(raw_title, soup, u.netloc)
    return _result(clean_role(raw_title, company), company, text, u.geturl(), "page")


def fetch_jd(url: str) -> dict:
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    u = urlparse(url)
    if not u.netloc or "." not in u.netloc:
        raise JDError("That does not look like a link.")
    host = u.netloc.lower()
    if any(w in host for w in WALLED):
        raise JDError("That site needs a login, so I can't read it. Paste the job description instead.")
    try:
        with httpx.Client() as client:
            res = None
            for fn in (from_greenhouse, from_lever, from_ashby):
                try:
                    res = fn(client, u)
                except Exception:
                    res = None
                if res and len(res["text"]) > 200:
                    break
                res = None
            if not res:
                res = from_page(client, u)
    except httpx.HTTPError as e:
        raise JDError(f"Network error while fetching the link ({type(e).__name__}). Paste the job description instead.")
    if len(res["text"]) < 300:
        raise JDError("The page loaded but I found almost no job text (it is probably rendered by JavaScript). Paste the job description instead.")
    res["title"] = clean_role(res["title"], res["company"])
    if res["source"] == "page":
        res["text"] = trim_boilerplate(res["text"])
    res["text"] = res["text"][:20000]
    return res
