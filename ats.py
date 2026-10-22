"""ATS checks: keyword coverage (before vs after), skills evidence, and PDF parse sanity.

There is no universal ATS score. This measures what parsers and recruiter keyword searches actually do:
does the job's must-have vocabulary appear, as plain text, in the resume.
"""
from __future__ import annotations

import re
from pathlib import Path

import tex_slots as TS

# term -> regex alternatives that count as a hit (case-insensitive, word-bounded)
ALIASES = {
    "machine learning": ["machine learning", r"\bML\b"],
    "ml": ["machine learning", r"\bML\b"],
    "deep learning": ["deep learning", "neural net"],
    "natural language processing": ["natural language processing", r"\bNLP\b"],
    "nlp": ["natural language processing", r"\bNLP\b"],
    "rest": [r"\bREST\b", "REST APIs?", "RESTful"],
    "rest apis": [r"\bREST\b", "REST APIs?", "RESTful"],
    "apis": [r"\bAPIs?\b"],
    "api": [r"\bAPIs?\b"],
    "postgres": ["postgres", "postgresql"],
    "postgresql": ["postgres", "postgresql"],
    "javascript": ["javascript", r"\bJS\b"],
    "typescript": ["typescript"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "sklearn": ["scikit-learn", "sklearn"],
    "aws": [r"\bAWS\b", "amazon web services"],
    "ci/cd": [r"CI/CD", "continuous integration"],
    "llm": [r"\bLLMs?\b", "large language model"],
    "llms": [r"\bLLMs?\b", "large language model"],
    "a/b testing": [r"A/B test", "experimentation"],
    "user interviews": [r"interview\w*"],
    "user research": [r"interview\w*", "user research"],
    "unit tests": ["unit tests?", "automated tests?", "pytest", "unit testing"],
    "unit testing": ["unit tests?", "automated tests?", "pytest", "unit testing"],
    "object-oriented": ["object-oriented", r"\bOOP\b"],
    "object-oriented design": ["object-oriented", r"\bOOP\b"],
    "oop": ["object-oriented", r"\bOOP\b"],
    "llm apis": ["Gemini API", "LLM API"],
    "data structures": ["data structures"],
    "algorithms": ["algorithms?"],
}

# vocabulary used to find keywords in a job description when the model did not supply any
VOCAB = """Python Java C++ C SQL JavaScript TypeScript Go Rust Scala R MATLAB Bash Swift Kotlin
PyTorch TensorFlow Keras scikit-learn XGBoost LightGBM pandas NumPy SciPy Spark Hadoop Kafka Airflow dbt Snowflake BigQuery Redshift
FastAPI Flask Django Spring React Node.js Next.js GraphQL REST gRPC PostgreSQL MySQL MongoDB Redis DynamoDB
AWS GCP Azure Docker Kubernetes Terraform Git GitHub CI/CD Linux microservices
machine learning deep learning NLP computer vision LLM LLMs embeddings transformers recommendation systems reinforcement learning
data structures algorithms distributed systems system design object-oriented API APIs ETL data pipelines data engineering
statistics regression classification A/B testing experimentation forecasting Tableau Power BI dashboards Excel
feature engineering model evaluation MLOps unit testing pytest Agile""".replace("\n", " ")
VOCAB_TERMS = sorted(set(re.findall(r"[A-Za-z0-9+#./-]+(?: (?=[a-z])[a-z-]+)*", VOCAB)), key=len, reverse=True)
# multi-word terms (written lowercase in VOCAB) are matched by the regex above; fix a few that need joining
MULTI = ["machine learning", "deep learning", "computer vision", "recommendation systems", "reinforcement learning", "data structures",
         "distributed systems", "system design", "data pipelines", "data engineering", "feature engineering", "model evaluation", "unit testing", "A/B testing"]
SINGLE = [t for t in VOCAB.split() if (t not in " ".join(MULTI).split() or t in ("Python", "Java", "SQL", "Git", "Spark")) and t not in ("C", "R", "Go", "API")]


def _pats(term: str) -> list[str]:
    alts = ALIASES.get(term.lower())
    if alts:
        return alts
    if re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", term) and term == term.lower():
        # plain English phrase: match word stems (scope features -> scoping feature)
        stem = lambda w: re.sub(r"(ing|ed|es|s|e)$", "", w) if len(w) > 4 else w
        return [r"\b" + r"\W+".join(re.escape(stem(w)) + r"\w*" for w in term.split())]
    t = re.escape(term)
    return [rf"(?<![A-Za-z0-9]){t}(?![A-Za-z0-9])"]


def has(term: str, text: str) -> bool:
    for p in _pats(term):
        pat = p if p.startswith(r"\b") else rf"(?<![A-Za-z0-9]){p}(?![A-Za-z0-9])"
        acronym = re.fullmatch(r"(\\b)?[A-Z/+#]{2,4}(\\b)?", p) is not None
        if re.search(pat, text, 0 if acronym else re.I):
            return True
    return False


def jd_terms(jd: str, model_keywords: list[str] | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for k in (model_keywords or []):
        k = k.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower()); terms.append(k)
    for t in MULTI + SINGLE:
        if t.lower() not in seen and has(t, jd):
            seen.add(t.lower()); terms.append(t)
    return terms


def tex_text(tex: str) -> str:
    body = tex[tex.index("\\begin{document}"):]
    body = re.sub(r"\\href\{[^}]*\}", "", body)
    body = body.replace("\\textsuperscript{2}", "2").replace("\\&", "&").replace("\\%", "%").replace("$\\cdot$", " ").replace("$|$", " ")
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", body)
    return re.sub(r"[{}\\$]", " ", body)


def pdf_text(pdf: Path) -> str:
    import pymupdf
    doc = pymupdf.open(pdf)
    return "\n".join(p.get_text() for p in doc)


def parse_check(text: str) -> list[dict]:
    """Things ATS parsers need. Each: {name, ok, detail}."""
    checks = []
    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    add("Text is selectable (not an image)", len(text.strip()) > 800, f"{len(text)} characters extracted")
    add("Email found", re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text) is not None)
    add("Phone found", re.search(r"\+?\d[\d\s().-]{8,}\d", text) is not None)
    heads = ["education", "experience", "skills", "projects"]
    miss = [h for h in heads if not re.search(rf"^\s*(technical )?{h}", text, re.I | re.M)]
    add("Standard section headings (Education, Skills, Experience, Projects)", not miss, ("missing: " + ", ".join(miss)) if miss else "")
    add("Graduation month and year", re.search(r"(Expected\s+)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d\d", text) is not None)
    add("Portfolio / GitHub / LinkedIn link", re.search(r"github\.com|linkedin\.com|\.github\.io", text, re.I) is not None)
    add("Degree spelled out (Bachelor of ...)", re.search(r"\bBachelor of (Arts|Science)\b", text) is not None, "ATS degree filters look for this wording")
    add("Date ranges use plain hyphens", re.search(r"(?:19|20)\d\d\s*[-]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:(?:19|20)\d\d|Present)", text) is not None)
    add("No en or em dashes (parsers split on them)", not re.search(r"[\u2013\u2014]", text), "found a special dash" if re.search(r"[\u2013\u2014]", text) else "")
    order = [m.start() for h in ("Education", "Technical Skills", "Experience", "Projects") for m in [re.search(rf"^\s*{h}\s*$", text, re.M)] if m]
    add("Sections read in a standard order", len(order) == 4 and order == sorted(order), "Education, Technical Skills, Experience, Projects")
    weird = re.findall(r"[\ufffd\u25a0\u2022\u00a0]{3,}|\(cid:\d+\)", text)
    add("No garbled characters", not weird)
    return checks


def analyze(jd: str, model_keywords: list[str], base_tex: str, final_text: str, master: str, skills_final: list[str], bullet_text: str) -> dict:
    terms = jd_terms(jd, model_keywords)
    base_text = tex_text(base_tex)
    rows = []
    for t in terms:
        rows.append({"term": t, "before": has(t, base_text), "after": has(t, final_text), "in_master": has(t, master)})
    n = len(rows) or 1
    pct = lambda k: round(100 * sum(r[k] for r in rows) / n)
    missing_supported = [r["term"] for r in rows if not r["after"] and r["in_master"]]
    gaps = [r["term"] for r in rows if not r["in_master"]]
    unevidenced = [s for s in skills_final if not has(s, bullet_text)]
    return {
        "terms": rows, "total": len(rows), "before_pct": pct("before"), "after_pct": pct("after"),
        "matched": [r["term"] for r in rows if r["after"]],
        "missing_supported": missing_supported, "gaps": gaps, "skills_not_in_bullets": unevidenced,
        "parse": parse_check(final_text),
    }
