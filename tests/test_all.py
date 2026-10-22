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
    for bad in ["a \\textbf{x}", "dash — here", "unbal **x", "x -- y", "{brace}"]:
        with pytest.raises(TS.MarkupError): TS.markup_to_latex(bad)
    assert TS.markup_to_latex("**8.6%** R² 5×") == "\\textbf{8.6\\%} R\\textsuperscript{2} 5$\\times$"


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
    assert rows[0] == "Company,Role,Resume" and rows[1] == "Acme,SWE Intern,Resumes/Acme - SWE Intern.pdf"
    assert (tmp_path / "apps" / "Resumes" / "Acme - SWE Intern.pdf").exists()
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
    assert got["token"] == "tok" and got["company"] == "Acme" and got["role"] == "ML Intern" and got["filename"] == "Acme - ML Intern.pdf" and "status" not in got and base64.b64decode(got["pdf_base64"])[:4] == b"%PDF"
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
    assert "Bachelor of Arts" in tex and "PyTorch" in tex and "TensorFlow" not in tex.split("\\begin{document}")[1].split("Experience")[0]
    b = T.compile_tex(tex, tmp_path, "r")
    assert b.ok and b.pages == 1 and 740 <= b.bottom <= T.PAGE_BOTTOM_MAX, (k, b.pages, b.bottom)
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
