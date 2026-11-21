import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
import tailor as T, tex_slots as TS, jd as J

ROOT = Path(__file__).parent.parent
ctx = T.make_ctx()


def parsed(k): return TS.parse((ROOT / T.BASES[k]["file"]).read_text())


FIX = ROOT / "tests" / "fixtures"
FIXTURES = sorted(f.stem for f in FIX.glob("*.tex"))


@pytest.mark.parametrize("fx", FIXTURES)
def test_identity_roundtrip(fx, tmp_path):
    k = fx.split("_")[0]
    p = TS.parse((FIX / f"{fx}.tex").read_text())
    base = T.compile_tex(p.text, tmp_path / "a", "r")
    prov = T.MockProvider()
    prop = prov.tailor(p, ctx, "")
    prop["skills"] = [{"label": T.plain_label(s.label), "items": s.items} for s in p.skills]
    plan = T.build_plan(p, prop, ctx, k)
    assert T.changed_slots(plan) == [], plan["warnings"]
    assert T.render_tex(p, plan) == p.text
    assert all(x["id"] for x in plan["projects"]["orig"])
    # force the regeneration paths
    plan["projects"]["new"] = [dict(x, bullets=list(x["bullets"])) for x in plan["projects"]["orig"]]
    plan["projects"]["orig"] = [{**x, "_": 1} for x in plan["projects"]["orig"]]
    plan["coursework"]["orig"] = {"completed": [], "in_progress": []}
    regen = T.render_tex(p, plan)
    b = T.compile_tex(regen, tmp_path / "b", "r")
    assert b.ok and b.pages == 1 and abs(b.bottom - base.bottom) < 0.5
    import pymupdf
    ta, tb = (pymupdf.open(x.pdf)[0].get_text() for x in (base, b))
    assert ta == tb


class Fake:
    name = "fake"
    def __init__(s, edit): s.edit = edit
    def pick_base(s, jd): return {"base": "ml", "reason": "t"}
    def tailor(s, parsed, ctx, jd, feedback=None):
        prop = T.MockProvider().tailor(parsed, ctx, jd)
        s.edit(prop); return prop


def test_rejects_invented_number_and_banned(tmp_path):
    def edit(prop):
        e = prop["entries"][0]["bullets"]
        e[0] = {"from_index": 0, "text": "Built a model with **99.9%** accuracy.", "source": ["made up quote that is absent"]}
        e[1] = {"from_index": 1, "text": "Taught sections and built Gradescope autograders.", "source": ["x" * 12]}
    r = T.generate("ml", "Machine learning job. " * 10, tmp_path, Fake(edit))
    plan = r["plan"]
    assert any("rejected" in w for w in plan["warnings"])
    assert T.changed_slots(plan) == []  # fell back to originals
    assert r["built"].ok


def test_accepts_grounded_rewrite(tmp_path):
    p = parsed("swe")
    orig = p.entries[0].bullets[1].markup
    new = orig.replace("Architected", "Designed")
    assert new != orig
    quote = next(l for l in ctx.master.splitlines() if "86 tests" in l)[:70]
    def edit(prop):
        prop["entries"][0]["bullets"][1] = {"from_index": 1, "text": new, "source": [quote]}
    r = T.generate("swe", "Backend job. " * 20, tmp_path, Fake(edit))
    assert "entry:e0" in T.changed_slots(r["plan"]) and r["built"].pages == 1
    assert "Designed an asynchronous" in (tmp_path / "resume.tex").read_text()


def test_markup_guards():
    for bad in ["a \\textbf{x}", "dash — here", "x -- y", "{brace}"]:
        with pytest.raises(TS.MarkupError): TS.markup_to_latex(bad)
    assert TS.markup_to_latex("8.6% R² 5×") == "8.6\\% R\\textsuperscript{2} 5$\\times$"
    assert TS.markup_to_latex("**8.6%** R² 5×") == "8.6\\% R\\textsuperscript{2} 5$\\times$"  # stray markers are dropped


def test_revert_to_fit(tmp_path):
    p = parsed("swe")
    long = ("Built a service that classifies videos and images using Gemini and stores each label with confidence and reasoning for audits " * 8)
    plan = T.build_plan(p, T.MockProvider().tailor(p, ctx, ""), ctx, "swe")
    plan["entries"]["e0"]["new"][0]["markup"] = long
    b = T.rebuild("swe", plan, tmp_path, set())
    assert b.pages == 2
    b2, rev = T.revert_to_fit(p, plan, tmp_path, set(), b, [])
    assert b2.pages == 1 and "entry:e0" in rev


GH = {"title": "ML Intern", "content": "&lt;p&gt;" + "We build models with PyTorch. " * 20 + "&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"}


def test_jd_greenhouse(monkeypatch):
    class R:
        def __init__(s, c, j): s.status_code, s._j = c, j; s.headers = {"content-type": "application/json"}; s.text = ""
        def json(s): return s._j
    monkeypatch.setattr(J, "_get", lambda c, url, **k: R(200, GH) if "boards-api.greenhouse.io/v1/boards/acme/jobs/123" in url else R(404, {}))
    r = J.fetch_jd("https://boards.greenhouse.io/acme/jobs/123")
    assert r["source"] == "greenhouse" and "PyTorch" in r["text"] and "- Python" in r["text"]


def test_jd_jsonld_and_walled(monkeypatch):
    desc = "&lt;p&gt;" + "Build backend services. " * 30 + "&lt;/p&gt;"
    page = '<html><head><script type="application/ld+json">' + json.dumps({"@type": "JobPosting", "title": "SWE Intern", "description": desc, "hiringOrganization": {"name": "Acme"}}) + "</script></head><body></body></html>"
    class R: status_code = 200; headers = {"content-type": "text/html"}; text = page
    monkeypatch.setattr(J, "_get", lambda c, url, **k: R())
    r = J.fetch_jd("https://careers.acme.com/job/1")
    assert r["company"] == "Acme" and r["source"] == "json-ld" and "backend" in r["text"]
    with pytest.raises(J.JDError): J.fetch_jd("https://www.linkedin.com/jobs/view/1")


def test_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as A
    monkeypatch.setattr(A, "OUT", tmp_path)
    c = TestClient(A.app)
    r = c.post("/api/generate", json={"base": "auto", "jd": "Machine learning engineer intern SentenceTransformers Embeddings LightGBM. " * 5, "mock": True})
    assert r.status_code == 200, r.text
    d = r.json(); assert d["ok"] and d["pages"] == 1
    assert c.get(f"/api/pdf/{d['job_id']}").content[:4] == b"%PDF"
    sid = next(s["id"] for s in d["slots"] if s["changed"])
    d2 = c.post("/api/revert", json={"job_id": d["job_id"], "reverted": [sid]}).json()
    assert not any(s["changed"] and not s["reverted"] for s in d2["slots"])
    assert c.get("/").status_code == 200 and c.get("/api/status").json()["latex"]
    assert c.post("/api/generate", json={"jd": "short"}).status_code == 400


def test_track_local(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as A, tracker
    monkeypatch.setattr(A, "OUT", tmp_path / "o"); monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps")
    monkeypatch.setattr(tracker, "google_ready", lambda: False)
    c = TestClient(A.app)
    d = c.post("/api/generate", json={"base": "swe", "jd": "Backend engineer intern FastAPI. " * 8, "mock": True}).json()
    r = c.post("/api/track", json={"job_id": d["job_id"], "company": "Acme", "role": "Acme - SWE Intern, Summer 2027 (USA) | Acme.jobs"})
    assert r.status_code == 200 and r.json()["mode"] == "local" and r.json()["role"] == "SWE Intern"
    rows = (tmp_path / "apps" / "tracker.csv").read_text().splitlines()
    import re
    assert rows[0] == "Company,Role,Resume" and re.fullmatch(r"Acme,SWE Intern,Resumes/Acme - SWE Intern - \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\.pdf", rows[1]), rows[1]
    assert len(list((tmp_path / "apps" / "Resumes").glob("Acme - SWE Intern - *.pdf"))) == 1
    assert c.post("/api/track", json={"job_id": d["job_id"], "company": "", "role": "x"}).status_code == 400


def test_track_webhook(tmp_path, monkeypatch):
    import threading, http.server, json as j, base64
    from fastapi.testclient import TestClient
    import app as A, tracker
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(s):
            got.update(j.loads(s.rfile.read(int(s.headers["Content-Length"]))))
            s.send_response(200); s.send_header("Content-Type", "application/json"); s.end_headers()
            s.wfile.write(b'{"ok": true, "drive_url": "https://drive.google.com/file/x"}')
        def log_message(*a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("TRACKER_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/exec"); monkeypatch.setenv("TRACKER_TOKEN", "tok")
    monkeypatch.setattr(A, "OUT", tmp_path / "o"); monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps")
    c = TestClient(A.app)
    d = c.post("/api/generate", json={"base": "ml", "jd": "ML engineer intern PyTorch. " * 10, "mock": True}).json()
    r = c.post("/api/track", json={"job_id": d["job_id"], "company": "Acme", "role": "ML Intern"})
    assert r.status_code == 200 and r.json()["mode"] == "google", r.text
    assert got["token"] == "tok" and got["company"] == "Acme" and got["role"] == "ML Intern" and got["filename"].startswith("Acme - ML Intern - ") and __import__("re").fullmatch(r"Acme - ML Intern - \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\.pdf", got["filename"]) and "status" not in got and base64.b64decode(got["pdf_base64"])[:4] == b"%PDF"
    srv.shutdown()


def test_clean_role():
    assert J.clean_role("Software Development Engineer Intern - Summer 2027 (USA) - Job ID: 10552937 | Amazon.jobs", "Amazon") == "Software Development Engineer Intern"
    assert J.clean_role("Amazon - Software Engineer Intern, 2027", "Amazon") == "Software Engineer Intern"
    assert J.clean_role("Machine Learning Engineer at Stripe", "Stripe") == "Machine Learning Engineer"


def test_ats_coverage_and_parse(tmp_path):
    import ats
    r = T.generate("swe", "Backend intern. Python, REST APIs, PostgreSQL, Kubernetes, React, machine learning. " * 3, tmp_path, T.MockProvider())
    rep = T.ats_for("swe", r["plan"], r["built"], r["jd"], set())
    assert rep["after_pct"] >= rep["before_pct"] and "Kubernetes" in rep["gaps"]
    assert all(c["ok"] for c in rep["parse"]), rep["parse"]
    assert ats.has("REST", "Built REST APIs") and not ats.has("ML", "html")


@pytest.mark.parametrize("fx", FIXTURES)
def test_project_styles_and_bank_ids(fx):
    p = TS.parse((FIX / f"{fx}.tex").read_text())
    want = "right" if fx.endswith("_new") else "link"
    assert all(b.style == want and b.url.startswith("https://github.com/") for b in p.projects.projects)
    ids = [T.bank_id_for(b, ctx.bank) for b in p.projects.projects]
    assert all(ids), (fx, [b.title for b in p.projects.projects], ids)
    assert all(e.company for e in p.entries) and all(e.bullets for e in p.entries)


@pytest.mark.parametrize("fx", [f for f in FIXTURES if f.endswith("_new")])
def test_generate_on_new_style(fx, tmp_path, monkeypatch):
    k = fx.split("_")[0]
    monkeypatch.setitem(T.BASES, k, dict(T.BASES.get(k, {"name": k, "blurb": ""}), file=str((FIX / f"{fx}.tex").relative_to(ROOT))))
    def edit(prop):  # swap in the second project only (same count) so project regeneration runs in the new style
        prop["projects"] = prop["projects"][::-1]
    r = T.generate(k, "Machine learning engineer intern Python PyTorch. " * 8, tmp_path, Fake(edit))
    assert r["built"].ok and r["built"].pages == 1, (r["built"].log, r["plan"]["warnings"])
    tex = (tmp_path / "resume.tex").read_text()
    assert "hfill" in tex and tex.count("\\href{https://github.com/vdkarthikeya/") >= 3
    assert "\\lk}" not in tex.split("\\begin{document}")[1]


# ---------------------------------------------------------------- v2 rules: ATS-first, at most three projects
@pytest.mark.parametrize("k", list(T.BASES))
def test_base_rules(k, tmp_path):
    import ats, pymupdf
    tex = (ROOT / T.BASES[k]["file"]).read_text()
    p = TS.parse(tex)
    assert 1 <= len(p.projects.projects) <= T.MAX_PROJECTS, f"{k} has {len(p.projects.projects)} projects"
    assert all(1 <= len(pb.bullets) <= T.MAX_PROJECT_BULLETS for pb in p.projects.projects)
    heads = [h for h in __import__("re").findall(r"\{((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* 20\d\d [-]+ [^}]*)\}", tex)]
    assert heads and all(" - " in h and "--" not in h for h in heads), heads
    assert "B.A. in Data Science and Applied Mathematics" in tex and "PyTorch" in tex and "TensorFlow" not in tex.split("\\section{Technical Skills}")[1]
    b = T.compile_tex(tex, tmp_path, "r")
    assert b.ok and b.pages == 1 and T.PAGE_BOTTOM_TARGET <= b.bottom <= T.PAGE_BOTTOM_MAX, (k, b.pages, b.bottom)
    text = "\n".join(pg.get_text() for pg in pymupdf.open(b.pdf))
    assert all(c["ok"] for c in ats.parse_check(text)), [c for c in ats.parse_check(text) if not c["ok"]]


def test_four_projects_rejected(tmp_path):
    k = "ds"
    parsed_ = parsed(k)
    ids = ["movie_genre", "housing_bias", "sb79", "spam"]
    prop = {"keywords": [], "summary": "", "gaps": [], "entries": [], "skills": [], "coursework": {"completed": [], "in_progress": []},
            "projects": [{"project_id": i, "bullets": [{"bank_id": None, "text": ctx.bank[i]["bullets"][0]["markup"], "source": []}]} for i in ids]}
    plan = T.build_plan(parsed_, prop, ctx, k)
    assert any("projects" in w.lower() for w in plan["warnings"]) and plan["projects"]["kind"] == "same"


def test_bank_bullets_are_clean():
    for pid, pr in ctx.bank.items():
        for b in pr["bullets"]:
            assert not T.check_bullet_text(b["markup"], ctx, 10_000), (b["id"], T.check_bullet_text(b["markup"], ctx, 10_000))


# ---------------------------------------------------------------- company and role from pasted text
META_CASES = [
    ("Data Scientist Intern - 2027\nNew York, NY\nApply\n\nAbout Hudson River Trading\nHudson River Trading (HRT) is a multi-asset class quantitative trading firm.",
     "https://job-boards.greenhouse.io/embed/job_app?for=wehrtyou&token=1", "Hudson River Trading", "Data Scientist Intern"),
    ("Data Science Intern\nRemote - USA\n\nAt Coinbase, our mission is to increase economic freedom in the world.",
     "", "Coinbase", "Data Science Intern"),
    ("Amazon - Software Development Engineer Intern - Summer 2027 (USA) - Job ID: 123456\n\nAmazon is an equal opportunity employer", "", "Amazon", "Software Development Engineer Intern"),
    ("Machine Learning Engineer Intern at Scale AI\n\nWe are hiring.", "", "Scale AI", "Machine Learning Engineer Intern"),
    ("Company: Stripe\nJob Title: Data Science Intern, Summer 2027\nLocation: SF", "", "Stripe", "Data Science Intern"),
    ("Software Engineering Intern, Summer 2027\nGoogle\nMountain View, CA, USA\n\nAbout the job\nGoogle's software engineers develop the next-generation technologies.", "", "Google", "Software Engineering Intern"),
    ("Sector Data Scientist Intern (Summer 2027) | New York\n\nCitadel is a leading global investment firm.\nAbout Citadel", "", "Citadel", "Sector Data Scientist Intern"),
    ("Product Manager Intern (Fall 2027 or Spring 2028)\n\nAbout Databricks\nDatabricks is the data and AI company.", "", "Databricks", "Product Manager Intern"),
    ("Quantitative Researcher Intern\nNew York\nJane Street is a quantitative trading firm and liquidity provider.", "", "Jane Street", "Quantitative Researcher Intern"),
]


@pytest.mark.parametrize("text,url,company,role", META_CASES)
def test_extract_meta(text, url, company, role):
    m = J.extract_meta(text, url)
    assert (m["company"], m["role"]) == (company, role), m


def test_extract_meta_unknown_and_slug():
    m = J.extract_meta("We are looking for someone great to join our team.")
    assert m["company"] == "" and m["confidence"]["company"] == "none"
    # no company cue in the text: fall back to the link, nicely capitalized
    m = J.extract_meta("Data Analyst Intern\nBuild dashboards and run SQL every day for the team.", "https://jobs.lever.co/hudson-river-trading/abc")
    assert m["company"] == "Hudson River Trading" and m["role"] == "Data Analyst Intern"
    assert J.pretty_slug("wehrtyou") == "Wehrtyou" and J.pretty_slug("scale-ai") == "Scale Ai"


def test_greenhouse_uses_real_company_name(monkeypatch):
    class R:
        def __init__(s, c, j): s.status_code, s._j = c, j; s.headers = {"content-type": "application/json"}; s.text = ""
        def json(s): return s._j
    def fake(c, url, **k):
        if url.endswith("/boards/wehrtyou/jobs/9"): return R(200, GH)
        if url.endswith("/boards/wehrtyou"): return R(200, {"name": "Hudson River Trading"})
        return R(404, {})
    monkeypatch.setattr(J, "_get", fake)
    assert J.fetch_jd("https://job-boards.greenhouse.io/embed/job_app?for=wehrtyou&token=9")["company"] == "Hudson River Trading"


def test_api_meta_and_track_fallback(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as A, tracker
    monkeypatch.setattr(A, "OUT", tmp_path / "o"); monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps")
    monkeypatch.setattr(tracker, "google_ready", lambda: False)
    c = TestClient(A.app)
    jdtext = "Data Science Intern\nRemote - USA\n\nAt Coinbase, our mission is to increase economic freedom. " + "We analyze data with Python and SQL. " * 6
    assert c.post("/api/jd-meta", json={"text": jdtext}).json()["company"] == "Coinbase"
    d = c.post("/api/generate", json={"base": "ds", "jd": jdtext, "mock": True}).json()
    assert d["meta"]["company"] == "Coinbase" and d["meta"]["role"] == "Data Science Intern"
    r = c.post("/api/track", json={"job_id": d["job_id"], "company": "", "role": ""})  # blank boxes still log correctly
    assert r.status_code == 200 and r.json()["company"] == "Coinbase" and r.json()["role"] == "Data Science Intern"


def test_no_project_heading_wraps(tmp_path):
    """Heading, tools and GitHub link stay on one line even with an overlong tools list (scaled, flagged)."""
    base = (T.ROOT / "resumes/ml.tex").read_text()
    ok = T.compile_tex(base, tmp_path / "a", "r")
    assert ok.ok and ok.heading_scaled == 0
    long_ = base.replace("\\emph{Python, PyTorch, OpenCV, OpenCLIP}", "\\emph{Python, PyTorch, OpenCV, OpenCLIP, CLIP, NumPy, pandas, scikit-learn, FastAPI, XGBoost, LightGBM, Jupyter}")
    assert long_ != base
    b = T.compile_tex(long_, tmp_path / "b", "r")
    import pymupdf
    words = pymupdf.open(b.pdf)[0].get_text("words")  # (x0, y0, x1, y1, word, ...)
    head_y = next(w[1] for w in words if w[4] == "SightLine")
    gh = [w for w in words if w[4] == "GitHub" and abs(w[1] - head_y) < 3]
    assert b.heading_scaled == 1 and gh, "GitHub link left the heading line"  # page count is not checked: the base is now exactly one full page


def test_coursework_never_labelled_in_progress():
    """Resume rule: no 'In progress' label anywhere. In-progress courses render as ordinary list items."""
    out = TS.render_coursework(["Data Structures", "Probability for Data Science"], ["Introduction to Machine Learning", "Data Engineering"])
    assert "In progress" not in out
    assert out.endswith("Probability for Data Science, Introduction to Machine Learning, Data Engineering")
    assert "In progress" not in TS.render_coursework(["Data Structures"], [])
    for k in T.BASES:
        assert "In progress" not in (ROOT / T.BASES[k]["file"]).read_text(), k


# ---- stray blank line regression (a bullet whose last line fills the width used to add an empty line)
def _sweep_doc(base_key: str) -> str:
    """Preamble of a base resume + 60 one-bullet entries whose text grows a few characters at a time, so some
    last lines end exactly at the right margin; plus 40 project headings with growing tool lists."""
    base = (ROOT / T.BASES[base_key]["file"]).read_text()
    pre = base[: base.index("\\begin{document}")]
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo sierra tango".split()
    body = ["\\begin{document}", "\\section{Experience}", "\\resumeSubHeadingListStart"]
    base_text = " ".join(words * 3)
    for n in range(60):
        txt = (base_text + " " + "x" * n) if n else base_text
        body.append("\\resumeCompactHeading{Company}{Role}{Remote}{2026}")
        body.append("\\resumeItemListStart\n\\resumeItem{" + txt + "}\n\\resumeItemListEnd\n")
    body.append("\\resumeSubHeadingListEnd")
    body.append("\\section{Projects}\n\\resumeSubHeadingListStart")
    for n in range(40):
        tech = ", ".join(["Python", "PyTorch", "OpenCV", "OpenCLIP", "pandas", "NumPy", "XGBoost"][: 2 + n % 6]) + "x" * (n // 2)
        body.append("\\resumeProjectHeading{\\textbf{Proj} $|$ \\emph{" + tech + "} \\hfill \\href{https://example.com}{\\uline{GitHub}}}")
        body.append("\\resumeItemListStart\n\\resumeItem{" + base_text[: 150 + 3 * n] + "}\n\\resumeItemListEnd\n")
    body.append("\\resumeSubHeadingListEnd\n\\end{document}")
    return pre + "\n".join(body) + "\n"


@pytest.mark.parametrize("k", list(T.BASES))
def test_no_stray_blank_lines_any_line_length(k, tmp_path):
    """Sweep many last-line widths through every base's macros: no gap may exceed the normal maximum."""
    b = T.compile_tex(_sweep_doc(k), tmp_path, "sweep")
    assert b.ok, b.log
    assert b.gap_issues == [], b.gap_issues[:5]


def test_macros_have_no_trailing_whitespace_in_definition():
    """The root cause: whitespace after the macro body became a space token at the end of the bullet paragraph."""
    import re
    for f in list((ROOT / "resumes").glob("*.tex")) + list((ROOT / "tests/fixtures").glob("*.tex")):
        s = f.read_text()
        for name in ("resumeItem", "classesList"):
            m = re.search(r"\\newcommand\{\\" + name + r"\}\[\d\]\{%?\n.*?\n\}\n", s, re.S)
            assert m, (f.name, name)
            body = m.group(0)
            assert re.search(r"\}%\n\}\n$", body), (f.name, name, "body must end with }% before the closing brace")


def test_resume_tailor_is_in_the_bank_again():
    """Nov 20, 2026: Resume Tailor is allowed as a project again (it was banned Nov 18). It lives in the bank so a tailored
    resume can pick it; the four bases do not list it. Its bullets follow the same rules as every other project."""
    bank, _ = T.load_bank()
    rt = bank["resume_tailor"]
    assert rt["title"] == "Resume Tailor" and rt["url"] == "https://github.com/vdkarthikeya/resume-tailor"
    assert 2 <= len(rt["bullets"]) <= 4 and T.NEVER_LIST_PROJECTS == set()
    for b in rt["bullets"]:
        low = b["markup"].lower()
        assert not T.check_bullet_text(b["markup"], ctx, 10_000), b["id"]
        assert "built with claude" not in low and "co-created" not in low, b["id"]
        assert "hindsight" not in low
    master = ctx.master.lower()
    assert all(t.lower() in master for t in rt["stack"]), [t for t in rt["stack"] if t.lower() not in master]
    for v in ("ml", "ds", "pm"):
        assert "textbf{Resume Tailor}" not in (T.ROOT / f"resumes/{v}.tex").read_text(), v  # only the SWE base lists it (Nov 20, asked by him)
    assert "textbf{Resume Tailor}" in (T.ROOT / "resumes/swe.tex").read_text()


def test_resume_tailor_can_be_picked_for_a_job(tmp_path):
    p = parsed("ml")
    prop = T.MockProvider().tailor(p, ctx, "")
    last = p.projects.projects[-1]
    n = len(last.bullets)
    prop["projects"][-1] = {"project_id": "resume_tailor", "bullets": [{"bank_id": b["id"]} for b in ctx.bank["resume_tailor"]["bullets"][:n]]}
    plan = T.build_plan(p, prop, ctx, "ml")
    assert not any("Projects" in w for w in plan["warnings"]), plan["warnings"]
    assert "projects" in T.changed_slots(plan) and plan["projects"]["new"][-1]["id"] == "resume_tailor"
    b = T.rebuild("ml", plan, tmp_path, set())
    assert b.ok and b.pages == 1 and "Resume Tailor" in "\n".join(pg.get_text() for pg in __import__("pymupdf").open(b.pdf))


# ---------------------------------------------------------------- speed: short answers, cacheable prompt, cheap base pick
def test_unchanged_bullets_need_only_from_index():
    p = parsed("ml")
    prop = T.MockProvider().tailor(p, ctx, "")
    for e in prop["entries"]:
        e["bullets"] = [{"from_index": b["from_index"]} for b in e["bullets"]]  # no text, no source
    plan = T.build_plan(p, prop, ctx, "ml")
    assert not any(s.startswith("entry:") for s in T.changed_slots(plan)), T.changed_slots(plan)
    assert not any("entry" in w.lower() or "bullet" in w.lower() for w in plan["warnings"]), plan["warnings"]
    # a reorder is also just indexes
    e0 = next(e for e in prop["entries"] if len(e["bullets"]) >= 2 and not T.is_locked_entry(next(x for x in p.entries if x.id == e["entry_id"])))
    e0["bullets"][0], e0["bullets"][1] = e0["bullets"][1], e0["bullets"][0]
    plan2 = T.build_plan(p, prop, ctx, "ml")
    assert f"entry:{e0['entry_id']}" in T.changed_slots(plan2)
    assert [x["kind"] for x in plan2["entries"][e0["entry_id"]]["new"][:2]] == ["moved", "moved"]


def test_bank_bullet_by_id_only():
    assert T.bank_bullet_markup(ctx, "hindsight_1") == ctx.bank["hindsight"]["bullets"][0]["markup"]
    assert T.bank_bullet_markup(ctx, "nope") == "" and T.bank_bullet_markup(ctx, None) == ""
    p = parsed("ml")
    prop = T.MockProvider().tailor(p, ctx, "")
    prop["projects"] = [{"project_id": T.bank_id_for(pb, ctx.bank), "bullets": [{"bank_id": b["id"]} for b in ctx.bank[T.bank_id_for(pb, ctx.bank)]["bullets"][:len(pb.bullets)]]} for pb in p.projects.projects]
    plan = T.build_plan(p, prop, ctx, "ml")
    assert not any("verifiable" in w or "Projects" in w for w in plan["warnings"]), plan["warnings"]


def test_locked_entry_not_sent_to_model():
    p = parsed("swe")
    sent = T.describe_base(p, ctx)["entries"]
    assert len(sent) == sum(1 for e in p.entries if not T.is_locked_entry(e)) and len(sent) < len(p.entries)
    assert not any("61A" in f"{e['company']} {e['role']}" for e in sent)


def test_prompt_prefix_is_stable_for_caching():
    p = parsed("ml")
    a = T.build_prompt_parts(p, ctx, "Job A. " * 30)
    b = T.build_prompt_parts(p, ctx, "A totally different job. " * 30, feedback="- too long")
    assert a[0] == b[0] and a[1] == b[1] and a[2] != b[2]  # only the last block changes between jobs and retries
    assert "MASTER DOC" in a[0] and "JOB DESCRIPTION" not in a[0] + a[1] and "JOB DESCRIPTION" in a[2]
    assert T.build_user_prompt(p, ctx, "Job A. " * 30) == "\n\n".join(a)


def test_fast_pick(monkeypatch):
    ml = "We train deep learning models in PyTorch. Machine learning, NLP, LLM, embedding, inference, neural networks, computer vision. " * 2
    assert T.pick_base_fast(ml)["base"] == "ml"
    assert T.pick_base_fast("We need a great teammate. Apply now.") is None            # unclear: the model decides
    assert T.pick_base_fast(ml + " product manager roadmap stakeholder " * 8) is None  # close call: the model decides
    monkeypatch.setenv("RESUME_FAST_PICK", "0")
    assert T.pick_base_fast(ml) is None


def test_timings_and_attempt_cap(tmp_path):
    calls = []
    class Always(Fake):
        def tailor(s, parsed, ctx, jd, feedback=None):
            calls.append(feedback); return super().tailor(parsed, ctx, jd, feedback)
    def edit(prop):  # shrink every skills line to one item so the page is under-filled and a retry is wanted every time
        for sk in prop["skills"]: sk["items"] = sk["items"][:1]
    r = T.generate("ml", "Machine learning job. " * 20, tmp_path, Always(edit))
    t = r["timings"]
    assert len(calls) <= T.DEFAULT_MAX_ATTEMPTS and t["attempts"] == len(calls) and t["total"] >= sum(t["llm"])
    assert len(t["llm"]) == len(t["compile"]) or len(t["compile"]) == len(t["llm"]) + 1  # +1 only when revert_to_fit recompiled


# ---------------------------------------------------------------- batch queue
import time as _time, threading as _th
from concurrent.futures import ThreadPoolExecutor as _Pool
from types import SimpleNamespace as _NS


def _client(tmp_path, monkeypatch, workers=3):
    from fastapi.testclient import TestClient
    import app as A
    monkeypatch.setattr(A, "OUT", tmp_path)
    monkeypatch.setattr(A, "EXEC", _Pool(max_workers=workers))
    monkeypatch.setattr(A, "QUEUE", {}); monkeypatch.setattr(A, "FUTURES", {})
    return A, TestClient(A.app)


def _fake_result(jd, base="ml"):
    return {"jd": jd, "base": base, "base_reason": None, "plan": None, "built": _NS(ok=True, pages=1, bottom=720.0, log="", pdf=None),
            "reverted": set(), "log": [], "parsed": None, "provider": "fake", "timings": {"total": 0.1}}


def _wait_idle(c, timeout=60):
    end = _time.time() + timeout
    while _time.time() < end:
        jobs = c.get("/api/jobs").json()["jobs"]
        if jobs and not any(j["status"] in ("queued", "running") for j in jobs):
            return jobs
        _time.sleep(0.05)
    raise AssertionError("queue did not finish: " + str(c.get("/api/jobs").json()))


JD = "Machine learning engineer intern. We use PyTorch, embeddings and LightGBM to build models. " * 3


def test_batch_validation(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch)
    assert c.post("/api/batch", json={"items": []}).status_code == 400
    assert c.post("/api/batch", json={"items": [{"jd": "short"}]}).status_code == 400
    assert c.post("/api/batch", json={"items": [{"jd": JD, "base": "nope"}]}).status_code == 400
    assert c.post("/api/batch", json={"items": [{"jd": JD}] * (A.MAX_BATCH + 1)}).status_code == 400
    assert c.get("/api/jobs/doesnotexist").status_code == 404


def test_batch_runs_jobs_in_parallel(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch, workers=3)
    live, peak, lock = [0], [0], _th.Lock()
    def slow(base, jd, outdir, provider, **k):
        with lock: live[0] += 1; peak[0] = max(peak[0], live[0])
        _time.sleep(0.4)
        with lock: live[0] -= 1
        return _fake_result(jd)
    monkeypatch.setattr(A.T, "generate", slow)
    t0 = _time.time()
    r = c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}] * 3, "mock": True})
    assert r.status_code == 200 and len(r.json()["jobs"]) == 3 and all(j["status"] == "queued" for j in r.json()["jobs"])
    jobs = _wait_idle(c)
    assert peak[0] >= 2 and _time.time() - t0 < 1.1  # three 0.4 s jobs finish in about 0.4 s, not 1.2 s
    assert [j["status"] for j in jobs] == ["done"] * 3 and all(j["pdf_url"].startswith("/api/pdf/") and "download=true" in j["pdf_url"] for j in jobs)


def test_batch_one_failure_does_not_stop_the_rest(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch)
    def gen(base, jd, outdir, provider, **k):
        if "BOOM" in jd: raise RuntimeError("model exploded")
        return _fake_result(jd)
    monkeypatch.setattr(A.T, "generate", gen)
    def fetch(url): raise A.jdmod.JDError("That site needs a login, so I can't read it.")
    monkeypatch.setattr(A.jdmod, "fetch_jd", fetch)
    c.post("/api/batch", json={"items": [{"jd": JD + "BOOM"}, {"jd": JD}, {"url": "https://www.linkedin.com/jobs/view/1"}], "mock": True})
    jobs = _wait_idle(c)
    by = {j["status"]: j for j in jobs}
    assert sorted(j["status"] for j in jobs) == ["done", "error", "error"]
    assert any("model exploded" in (j["error"] or "") for j in jobs) and any("needs a login" in (j["error"] or "") for j in jobs)


def test_batch_cancel_queued_job(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch, workers=1)
    gate = _th.Event()
    def gen(base, jd, outdir, provider, **k):
        gate.wait(5); return _fake_result(jd)
    monkeypatch.setattr(A.T, "generate", gen)
    ids = [j["id"] for j in c.post("/api/batch", json={"items": [{"jd": JD}, {"jd": JD}], "mock": True}).json()["jobs"]]
    assert c.post(f"/api/jobs/{ids[1]}/cancel").json()["status"] == "cancelled"
    assert c.post(f"/api/jobs/{ids[0]}/cancel").json()["status"] in ("queued", "running")  # already running: cannot be cancelled
    gate.set()
    jobs = _wait_idle(c)
    assert {j["id"]: j["status"] for j in jobs} == {ids[0]: "done", ids[1]: "cancelled"}
    assert len(c.post("/api/jobs/clear").json()["jobs"]) == 0


def test_batch_end_to_end_with_real_pdf(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch)
    r = c.post("/api/batch", json={"items": [{"jd": JD, "base": "auto"}, {"jd": JD.replace("Machine learning", "Backend software"), "base": "swe"}], "mock": True})
    assert r.status_code == 200
    jobs = _wait_idle(c)
    assert [j["status"] for j in jobs] == ["done", "done"], [j.get("error") for j in jobs]
    for j in jobs:
        d = c.get(f"/api/jobs/{j['id']}").json()
        assert d["ok"] and d["pages"] == 1 and d["job_id"] == j["id"] and d["timings"]["total"] >= 0
        assert c.get(j["pdf_url"]).content[:4] == b"%PDF"


def test_queue_row_shows_tracked_flag(tmp_path, monkeypatch):
    import tracker
    A, c = _client(tmp_path / "o", monkeypatch)
    monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps"); monkeypatch.setattr(tracker, "google_ready", lambda: False)
    c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}, {"jd": JD, "base": "swe"}], "mock": True})
    jobs = _wait_idle(c)
    assert [j["tracked"] for j in jobs] == [False, False]
    r = c.post("/api/track", json={"job_id": jobs[0]["id"], "company": "Acme", "role": "ML Intern"})
    assert r.status_code == 200
    rows = {j["id"]: j for j in c.get("/api/jobs").json()["jobs"]}
    assert rows[jobs[0]["id"]]["tracked"] is True and rows[jobs[0]["id"]]["company"] == "Acme" and rows[jobs[0]["id"]]["role"] == "ML Intern"
    assert rows[jobs[1]["id"]]["tracked"] is False
    assert c.post("/api/track", json={"job_id": jobs[1]["id"], "company": "", "role": ""}).status_code in (200, 400)  # blank boxes: falls back to the job text, else a clear error


# ---------------------------------------------------------------- Nov 20 later: retry, auto-track, duplicates, saved queue, email, sync check
JD_ACME = "Acme Corp\nMachine Learning Engineer Intern\n\nAbout Acme Corp\nAcme Corp is hiring. We use PyTorch, embeddings and LightGBM to build models. " * 2


def test_retry_failed_job(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch)
    calls = {"n": 0}
    real = A.T.generate
    def flaky(base, jd, out, provider):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(base, jd, out, provider)
    monkeypatch.setattr(A.T, "generate", flaky)
    c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}], "mock": True})
    jobs = _wait_idle(c)
    assert jobs[0]["status"] == "error"
    assert c.post(f"/api/jobs/{jobs[0]['id']}/retry").status_code == 200
    jobs = _wait_idle(c)
    assert len(jobs) == 1 and jobs[0]["status"] == "done" and jobs[0]["id"] != ""
    assert c.post(f"/api/jobs/{jobs[0]['id']}/retry").status_code == 409  # a finished job is not retried
    assert c.post("/api/jobs/nope/retry").status_code == 404


def test_duplicate_warning_and_force(tmp_path, monkeypatch):
    import tracker
    A, c = _client(tmp_path / "o", monkeypatch)
    monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps"); monkeypatch.setattr(tracker, "google_ready", lambda: False)
    c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}], "mock": True})
    j1 = _wait_idle(c)[0]
    assert c.post("/api/track", json={"job_id": j1["id"], "company": "Acme", "role": "ML Intern"}).status_code == 200
    assert tracker.logged_before("acme", "ML Intern") and not tracker.logged_before("Other", "ML Intern")
    c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}], "mock": True})
    j2 = [j for j in _wait_idle(c) if j["id"] != j1["id"]][0]
    r = c.post("/api/track", json={"job_id": j2["id"], "company": "Acme", "role": "ML Intern"})
    assert r.status_code == 409 and r.json()["detail"].startswith("Already logged")
    assert c.post("/api/track", json={"job_id": j2["id"], "company": "Acme", "role": "ML Intern", "force": True}).status_code == 200


def test_auto_track_logs_once_and_skips_duplicates(tmp_path, monkeypatch):
    import tracker
    A, c = _client(tmp_path / "o", monkeypatch)
    monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps"); monkeypatch.setattr(tracker, "google_ready", lambda: False)
    c.post("/api/batch", json={"items": [{"jd": JD_ACME, "base": "ml"}], "mock": True, "auto_track": True})
    row = _wait_idle(c)[0]
    assert row["status"] == "done" and row["company"] == "Acme" and row["tracked"] is True and row["duplicate"] is False
    c.post("/api/batch", json={"items": [{"jd": JD_ACME, "base": "ml"}], "mock": True, "auto_track": True})
    rows = _wait_idle(c)
    second = [r for r in rows if r["id"] != row["id"]][0]
    assert second["status"] == "done" and second["tracked"] is False and second["duplicate"] is True
    assert len(list((tmp_path / "apps" / "Resumes").glob("*.pdf"))) == 1


def test_auto_track_failure_keeps_the_resume(tmp_path, monkeypatch):
    import tracker
    A, c = _client(tmp_path / "o", monkeypatch)
    monkeypatch.setattr(tracker, "LOCAL_DIR", tmp_path / "apps")
    def bad(*a, **k): raise RuntimeError("sheet down")
    monkeypatch.setattr(tracker, "log_application", bad)
    c.post("/api/batch", json={"items": [{"jd": JD_ACME, "base": "ml"}], "mock": True, "auto_track": True})
    row = _wait_idle(c)[0]
    assert row["status"] == "done" and row["tracked"] is False and "sheet down" in row["track_error"]


def test_queue_survives_restart(tmp_path, monkeypatch):
    A, c = _client(tmp_path, monkeypatch)
    c.post("/api/batch", json={"items": [{"jd": JD, "base": "ml"}], "mock": True})
    done = _wait_idle(c)[0]
    assert (tmp_path / "queue.json").exists() and (tmp_path / done["id"] / "job.json").exists()
    # a job that was running when the server stopped
    q = json.loads((tmp_path / "queue.json").read_text())
    q.append(dict(done, id="halfway", status="running", ok=None, pdf_url=None))
    (tmp_path / "queue.json").write_text(json.dumps(q))
    monkeypatch.setattr(A, "QUEUE", {}); monkeypatch.setattr(A, "FUTURES", {})
    A._load_queue()
    rows = {r["id"]: r for r in c.get("/api/jobs").json()["jobs"]}
    assert rows[done["id"]]["status"] == "done" and rows["halfway"]["status"] == "error" and "restarted" in rows["halfway"]["error"]
    assert c.get(rows[done["id"]]["pdf_url"]).content[:4] == b"%PDF"        # the finished PDF still downloads
    A.JOBS.pop(done["id"], None)                                            # a real restart empties the in-memory results
    assert c.get(f"/api/jobs/{done['id']}").status_code == 409              # the review panel needs a re-run
    assert c.post(f"/api/jobs/{done['id']}/cancel").status_code == 200
    (tmp_path / "halfway").mkdir(); (tmp_path / "halfway" / "job.json").write_text(json.dumps({"jd": JD, "url": "", "base": "ml", "mock": True}))
    assert c.post("/api/jobs/halfway/retry").status_code == 200
    assert _wait_idle(c)[-1]["status"] == "done"


def test_js_shell_pages_are_refused(monkeypatch):
    assert J.looks_like_js_shell("Loading...") and J.looks_like_js_shell("You need to enable JavaScript to run this app. " * 3)
    assert not J.looks_like_js_shell("Data Scientist Intern. " * 200)  # a long real post is never a shell
    monkeypatch.setattr(J, "from_greenhouse", lambda c, u: None); monkeypatch.setattr(J, "from_lever", lambda c, u: None); monkeypatch.setattr(J, "from_ashby", lambda c, u: None)
    monkeypatch.setattr(J, "from_page", lambda c, u: {"title": "", "company": "", "text": ("Please enable JavaScript to view this page. " * 12), "source": "page", "url": u})
    with pytest.raises(J.JDError, match="JavaScript"):
        J.fetch_jd("https://jobs.example.com/123")


def test_email_draft_uses_only_what_is_on_the_resume(tmp_path, monkeypatch):
    import email_draft
    e = email_draft.build("Acme Corp", "ML Intern", ["PyTorch", "Kubernetes", "LightGBM", "Python", "SQL"], "I used PyTorch, LightGBM and Python daily.")
    assert e["keywords"] == ["PyTorch", "LightGBM", "Python"] and "Kubernetes" not in e["body"]
    assert "Acme Corp" in e["body"] and "ML Intern" in e["subject"] and not any(ch in e["body"] + e["subject"] for ch in "–—")
    assert len(e["body"].split()) < 90
    A, c = _client(tmp_path, monkeypatch)
    c.post("/api/batch", json={"items": [{"jd": JD_ACME, "base": "ml"}], "mock": True})
    row = _wait_idle(c)[0]
    d = c.get(f"/api/email/{row['id']}").json()
    assert "Acme" in d["body"] and d["subject"].startswith("Machine Learning Engineer Intern")
    assert c.get("/api/email/nope").status_code == 404


def test_sync_check_repo_is_consistent():
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_check
    assert sync_check.check_repo(ROOT) == []


def test_sync_check_catches_drift(tmp_path):
    import shutil
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_check
    for n in ("bank", "resumes"):
        shutil.copytree(ROOT / n, tmp_path / n)
    shutil.copy(ROOT / "master_doc.md", tmp_path / "master_doc.md")
    bank = json.loads((tmp_path / "bank/projects.json").read_text())
    rt = next(p for p in bank if p["id"] == "resume_tailor")
    rt["bullets"][0]["markup"] = "Built a tool in 9,999 lines — Built with Claude."
    (tmp_path / "bank/projects.json").write_text(json.dumps(bank))
    tex = (tmp_path / "resumes/swe.tex").read_text()
    (tmp_path / "resumes/swe.tex").write_text(tex.replace("textbf{Next Step}", "textbf{Ghost Project}", 1))
    bad = "\n".join(sync_check.check_repo(tmp_path))
    assert "9,999" in bad and "Built with Claude" in bad and "dash" in bad and "Ghost Project" in bad
    site = tmp_path / "site"; (site / "resumes/src").mkdir(parents=True)
    (site / "resumes/src/resume_swe.tex").write_text("old")
    out = "\n".join(sync_check.check_site(tmp_path, site))
    assert "resume_swe.tex differs" in out and "resume_ml.tex is missing" in out


def test_no_bold_in_bullets():
    """Nov 21, 2026 rule (replaces the Nov 20 numbers-only-bold rule): bullets are plain sentences, no bold anywhere in them."""
    import re, json
    assert TS.markup_to_latex("Built a **Python** app, **47%** faster, **CLIP ViT-B/32**") == "Built a Python app, 47\\% faster, CLIP ViT-B/32"
    assert TS.latex_to_markup("Cut \\textbf{30\\%} on \\textbf{25} jobs") == "Cut 30% on 25 jobs"
    for p in json.loads((T.ROOT / "bank/projects.json").read_text()):
        for b in p["bullets"]:
            assert "**" not in b["markup"], b["id"]
    for v in ("ml", "ds", "swe", "pm"):
        for line in (T.ROOT / f"resumes/{v}.tex").read_text().splitlines():
            m = re.match(r"\s*\\resumeItem\{(.*)\}\s*$", line)
            if m and "Relevant Coursework" not in line:
                mk = TS.latex_to_markup(m.group(1))
                assert "textbf" not in m.group(1) and "**" not in mk, (v, mk[:70])


def test_nov21_resume_rules():
    """Nov 21, 2026: Guang Labs and IDX Exchange have the same number of bullets on every version, CDSS is spelled out, every GitHub link is underlined."""
    import re
    def bullets(tex, org):
        m = re.search(r"\\resumeCompactHeading\s*\{" + re.escape(org) + r"\}.*?\\resumeItemListEnd", tex, re.S)
        return len(re.findall(r"\\resumeItem\{", m.group(0))) if m else None
    for v in ("ml", "ds", "swe", "pm"):
        tex = (T.ROOT / f"resumes/{v}.tex").read_text()
        g, i = bullets(tex, "Guang Labs"), bullets(tex, "IDX Exchange")
        assert g is None or i is None or g == i, (v, "Guang Labs", g, "IDX", i)
        assert "{UC Berkeley CDSS}" not in tex and "UC Berkeley College of Computing, Data Science, and Society" in tex, v
        assert "UC Berkeley EECS" not in tex and ("CS 61A" not in tex or "UC Berkeley Electrical Engineering and Computer Sciences" in tex), v  # EECS spelled out for context
        for m in re.finditer(r"(\\uline\{)?GitHub\}", tex):
            assert m.group(1), (v, "GitHub link is not underlined")
