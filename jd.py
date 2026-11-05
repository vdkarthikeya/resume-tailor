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
    company = d.get("company_name") or ""
    if not company:  # the board slug is often not the company name (wehrtyou = Hudson River Trading)
        try:
            b = _get(client, f"https://boards-api.greenhouse.io/v1/boards/{board}")
            company = (b.json().get("name") or "") if b.status_code == 200 else ""
        except Exception:
            company = ""
    return _result(d.get("title"), company or pretty_slug(board), text, u.geturl(), "greenhouse")


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
    return _result(d.get("text"), pretty_slug(parts[0]), "\n\n".join(c for c in chunks if c), u.geturl(), "lever")


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
            return _result(j.get("title"), pretty_slug(org), text, u.geturl(), "ashby")
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
    guess = extract_meta(res["text"], url)
    if not res["company"] or (res["source"] == "page" and guess["company"] and guess["confidence"]["company"] == "high"):
        res["company"] = guess["company"] or res["company"]
    res["title"] = clean_role(res["title"], res["company"]) or guess["role"]
    if res["source"] == "page":
        res["text"] = trim_boilerplate(res["text"])
    res["text"] = res["text"][:20000]
    return res



# ---------------------------------------------------------------- company and role from pasted text
ROLE_WORDS = (
    r"intern(?:ship)?|co-?op|engineer|scientist|analyst|developer|researcher|manager|associate|specialist|designer|architect|"
    r"consultant|coordinator|fellow|apprentice|trainee|quant(?:itative)?(?:\s+(?:researcher|trader|developer|analyst))?|trader|"
    r"director|strategist|programmer|statistician|economist|technician|administrator|assistant|lead"
)
ROLE_RE = re.compile(rf"\b(?:{ROLE_WORDS})\b", re.I)
NOT_TITLE = re.compile(
    r"\b(apply|equal opportunity|we are|we're|you will|you'll|responsibilit|qualification|requirements?|about (the|us|you|this)|"
    r"benefits|salary|compensation|posted|location|click|sign in|log ?in|careers?|home|search|overview|description|"
    r"what you|who you|what we|why you|learn more|share|save|view all|back to|http|www\.)\b", re.I)
STOP_COMPANY = {
    "we", "the", "our", "this", "that", "you", "your", "about", "overview", "job", "description", "role", "team", "summary", "position",
    "responsibilities", "qualifications", "requirements", "benefits", "apply", "intern", "internship", "company", "us", "who", "what", "why",
    "if", "as", "an", "a", "in", "at", "to", "it", "i", "join", "welcome", "location", "salary", "equal", "opportunity", "employer", "united",
    "states", "usa", "remote", "new", "work", "life", "all", "each", "every", "any", "one", "two", "great", "high", "data", "software",
    "machine", "learning", "business", "technology", "global", "leading", "fast", "growing", "mission", "values", "culture",
}
NAME = r"[A-Z][\w&.'’\-]*(?:\s+(?:[A-Z][\w&.'’\-]*|of|and|&|the|for)){0,4}"
COMPANY_PATTERNS = [
    # (regex, weight, group) applied per line; weights say how reliable the cue is
    (re.compile(r"^\s*(?:company|employer|organi[sz]ation|hiring company|company name)\s*[:\-]\s*(.{2,60}?)\s*$", re.I), 9),
    (re.compile(rf"^\s*About\s+(?:the\s+company[:,\s\-]+)?({NAME})\s*:?\s*$"), 8),
    (re.compile(rf"^\s*About\s+(?:the\s+company[:,\s\-]+|us[:,\s\-]+)({NAME})\s*:?\s*$"), 7),
    (re.compile(rf"\bAt\s+({NAME}),\s+(?:we|our|you|your|every|each|the)\b"), 7),
    (re.compile(rf"\b({NAME})\s+is\s+(?:an?\s+|the\s+|one of\s+|now\s+)?(?:equal opportunity|equal-opportunity|an equal|proud|committed|looking|seeking|hiring|building|a leading|a global|a fast|a technology|a quantitative|a research|an? \w+ (?:company|firm|platform|team|organization|startup))"), 6),
    (re.compile(rf"\b({NAME})\s+(?:is|was)\s+(?:founded|started|established|headquartered|based)\b"), 6),
    (re.compile(r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})['’]s\s+(?:mission|vision|software engineers|engineers|teams?|products?|platform|customers|employees|culture|values|data scientists)\b"), 5),
    (re.compile(rf"\bJoin\s+(?:the\s+team\s+at\s+|us\s+at\s+)?({NAME})(?:\s*[!.,]|\s+(?:as|and|today|to)\b)"), 5),
    (re.compile(rf"\bWelcome to\s+({NAME})\b"), 5),
    (re.compile(rf"^\s*(?:Why|Life at|Working at|Careers at|Jobs at)\s+({NAME})\s*\??\s*$"), 5),
    (re.compile(rf"(?:©|\(c\)|copyright)\s*(?:20\d\d\s*)?({NAME})", re.I), 4),
    (re.compile(rf"\bat\s+({NAME})\s*$"), 3),
    (re.compile(rf"\b({NAME})\s+(?:employees|engineers|teams?|careers?)\b"), 1),
]
PLACES = {"new york", "san francisco", "seattle", "chicago", "boston", "austin", "los angeles", "london", "remote", "hybrid", "mountain view", "menlo park", "palo alto", "san jose", "redmond", "new york city", "nyc", "sunnyvale", "cupertino", "atlanta", "denver", "washington", "houston", "toronto", "bangalore", "san mateo", "santa clara", "irvine", "pittsburgh", "miami", "dallas", "philadelphia", "united states"}
LEADING_TITLE_AT = re.compile(rf"^\s*(?P<title>.+?)\s+(?:at|@)\s+(?P<company>{NAME})\s*$")
COMPANY_SUFFIX = re.compile(r"[\s,]+(?:inc\.?|llc|l\.l\.c\.|ltd\.?|corp\.?|corporation|co\.|company|gmbh|plc|lp|the)\s*$", re.I)


def pretty_slug(slug: str) -> str:
    """'hudson-river-trading' -> 'Hudson River Trading'; lone lowercase slugs are only capitalized."""
    slug = (slug or "").strip()
    if not slug:
        return ""
    if re.search(r"[-_]", slug):
        return " ".join(w.capitalize() for w in re.split(r"[-_]+", slug) if w)
    return slug.capitalize() if slug.islower() else slug


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _clean_company(c: str) -> str:
    c = re.sub(r"\s+", " ", c).strip(" \t:,;.-–—|\"'“”")
    c = re.sub(r"[’']s$", "", c)
    c = COMPANY_SUFFIX.sub("", c).strip(" ,.")
    words = c.split()
    while words and words[0].lower() in STOP_COMPANY:
        words = words[1:]
    while words and words[-1].lower() in STOP_COMPANY | {"team", "teams", "careers"}:
        words = words[:-1]
    c = " ".join(words)
    if not c or len(c) < 2 or len(c) > 45 or c.lower() in STOP_COMPANY:
        return ""
    return c


def _slug_hint(url: str) -> str:
    if not url:
        return ""
    u = urlparse(url if "://" in url else "https://" + url)
    qs = parse_qs(u.query)
    if "for" in qs:  # greenhouse embed
        return qs["for"][0]
    host = u.netloc.lower()
    parts = [p for p in u.path.strip("/").split("/") if p]
    if any(k in host for k in ("greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "workable.com", "jobvite.com")) and parts:
        return parts[0]
    labels = [x for x in host.split(".") if x not in ("www", "careers", "jobs", "com", "io", "co", "net", "org", "boards", "apply", "job", "us")]
    return labels[0] if labels else ""


def _role_from_line(line: str) -> str:
    """Turn a heading-like line into a clean job title, or '' if it does not look like one."""
    l = line.strip(" \t-–—|•*#:")
    if not l or len(l) > 110 or l.endswith((".", "!", "?")) or NOT_TITLE.search(l):
        return ""
    if len(l.split()) > 14:
        return ""
    # "Title | Location" or "Title - Summer 2027 - New York": keep the part(s) that read as the title
    pieces = [p.strip() for p in re.split(r"\s+[|–—]\s+|\s+-\s+|\s*\|\s*", l) if p.strip()]
    keep = []
    for p in pieces:
        if re.fullmatch(r"(?i)(summer|fall|winter|spring)?\s*20\d\d(\s*\(.*\))?|remote|hybrid|on-?site|full[- ]time|part[- ]time|[A-Z][\w .]+,\s*[A-Z]{2}(,\s*\w+)?|[A-Z][\w .]+,\s*(USA|United States|UK|Canada|India)", p):
            continue
        keep.append(p)
    # take the first piece that reads as a title ("Amazon - SDE Intern - Summer 2027" -> the SDE Intern piece)
    for p in (keep or [l]):
        cand = clean_role(p)
        if cand and ROLE_RE.search(cand) and not NOT_TITLE.search(cand):
            return cand
    return ""


def extract_meta(text: str, url: str = "") -> dict:
    """Best guess at {company, role} from pasted job text (and an optional link).

    Returns {"company", "role", "confidence": {"company": high|medium|low|none, "role": ...}}.
    Heuristic only: the UI shows both in editable boxes, and low confidence is flagged there.
    """
    text = (text or "").replace("\r", "")
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in text.split("\n")]
    lines = [l for l in lines if l]
    head = lines[:25]
    slug = _slug_hint(url)

    # ---- role
    roles: dict[str, float] = {}

    def add_role(r: str, w: float):
        if r:
            roles[r] = roles.get(r, 0) + w

    first = lines[0] if lines else ""
    m = LEADING_TITLE_AT.match(first)
    title_at_company = ""
    if m and ROLE_RE.search(m.group("title")):
        add_role(_role_from_line(m.group("title")), 10)
        title_at_company = m.group("company")
    for i, l in enumerate(head):
        lab = re.match(r"^\s*(?:job\s*title|position(?:\s*title)?|role|title|job)\s*[:\-]\s*(.{3,90})$", l, re.I)
        if lab:
            add_role(_role_from_line(lab.group(1)), 12)
            continue
        r = _role_from_line(l)
        if r:
            w = 8 - min(i, 12) * 0.5  # earlier lines are more likely the title
            if re.search(r"\bintern", r, re.I):
                w += 1
            if len(r.split()) <= 7:
                w += 0.5
            add_role(r, w)
    for m in re.finditer(rf"(?:looking for|seeking|hiring|searching for|join (?:us|our [\w ]{{1,30}}) as)\s+(?:an?|our|the)\s+((?:[A-Z][\w/&+.\-]*\s+){{0,5}}(?:{ROLE_WORDS})(?:\s+Intern)?)", text):
        add_role(_role_from_line(m.group(1)), 3)
    for m in re.finditer(rf"\bas an?\s+((?:[A-Z][\w/&+.\-]*\s+){{0,5}}(?:{ROLE_WORDS}))\b", text[:6000]):
        add_role(_role_from_line(m.group(1)), 2)
    role = max(roles, key=lambda k: roles[k]) if roles else ""
    role_conf = "none" if not role else ("high" if roles[role] >= 7 else "medium" if roles[role] >= 3 else "low")

    # ---- company
    cands: dict[str, float] = {}

    def add_co(c: str, w: float):
        c = _clean_company(c)
        if c and not ROLE_RE.fullmatch(c.strip()):
            key = next((k for k in cands if _norm(k) == _norm(c)), c)
            cands[key] = cands.get(key, 0) + w

    if title_at_company:
        add_co(title_at_company, 10)
    for l in lines[:120]:
        for rx, w in COMPANY_PATTERNS:
            for m in rx.finditer(l):
                add_co(m.group(1), w)
    # a short capitalized first line that is not the title is often just the company name
    for i, l in enumerate(lines[:4]):
        if re.fullmatch(rf"{NAME}", l) and not ROLE_RE.search(l) and len(l.split()) <= 4 and l.lower() not in PLACES:
            add_co(l, 3.5 - i * 0.5)
    # the link's slug backs up a candidate that matches it, or is the fallback
    if slug:
        ns = _norm(slug)
        for k in list(cands):
            nk = _norm(k)
            if nk and (nk in ns or ns in nk):
                cands[k] += 6
    company = max(cands, key=lambda k: (cands[k], -len(k))) if cands else ""
    if cands:
        top = cands[company]
        company_conf = "high" if top >= 8 else "medium" if top >= 5 else "low"
    else:
        company = pretty_slug(slug) if slug and _norm(slug) not in {"", "jobs", "careers"} else ""
        company_conf = "low" if company else "none"
    return {"company": company, "role": role, "confidence": {"company": company_conf, "role": role_conf}}
