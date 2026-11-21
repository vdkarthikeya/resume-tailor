"""Local resume tailor. Run: uvicorn app:app --port 8000"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import jd as jdmod
import tracker
import tailor as T
import tex_slots as TS

ROOT = Path(__file__).parent
OUT = ROOT / "out"
app = FastAPI(title="Resume Tailor")
JOBS: dict[str, dict] = {}
PROVIDER_OVERRIDE = None  # tests set this

# Batch queue. Jobs wait here, a small pool of worker threads runs them side by side, and the page polls /api/jobs.
# Keep the pool at 3 on a Claude subscription (each model call is a separate `claude -p` process); raise it with an API key.
WORKERS = max(1, int(os.environ.get("RESUME_WORKERS", "3")))
EXEC = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="tailor")
QUEUE: dict[str, dict] = {}  # job_id -> queue entry, in submit order
FUTURES: dict[str, Future] = {}
QLOCK = threading.Lock()
MAX_BATCH = 25


class FetchReq(BaseModel):
    url: str


class GenReq(BaseModel):
    base: str = "auto"
    jd: str
    mock: bool = False
    url: str = ""


class MetaReq(BaseModel):
    text: str
    url: str = ""


class BatchItem(BaseModel):
    jd: str = ""    # pasted job text, or leave empty and give a url (the worker fetches it)
    url: str = ""
    base: str = "auto"


class BatchReq(BaseModel):
    items: list[BatchItem]
    mock: bool = False


class RevertReq(BaseModel):
    job_id: str
    reverted: list[str] = []


def slots_view(plan: dict, reverted: set[str]) -> list[dict]:
    out = []
    for k, e in plan["entries"].items():
        sid = f"entry:{k}"
        changed = [b["markup"] for b in e["new"]] != e["orig"]
        out.append({"id": sid, "group": "Experience", "label": e["label"], "changed": changed, "reverted": sid in reverted,
                    "before": e["orig"], "after": [b["markup"] for b in e["new"]],
                    "notes": [{"kind": b["kind"], "sources": b["sources"]} for b in e["new"]]})
    for k, s in plan["skills"].items():
        out.append({"id": k, "group": "Skills", "label": s["label"], "changed": s["new"] != s["orig"], "reverted": k in reverted,
                    "before": [", ".join(s["orig"])], "after": [", ".join(s["new"])], "notes": []})
    c = plan["coursework"]
    f = lambda x: [", ".join(x["completed"] + x["in_progress"])]
    out.append({"id": "course", "group": "Coursework", "label": "Relevant coursework", "changed": c["new"] != c["orig"], "reverted": "course" in reverted,
                "before": f(c["orig"]), "after": f(c["new"]), "notes": []})
    p = plan["projects"]
    fp = lambda lst: [f"{x['title'].replace(chr(92)+'&', '&')}: " + " / ".join(x["bullets"]) for x in lst]
    out.append({"id": "projects", "group": "Projects", "label": "Projects", "changed": p["new"] != p["orig"], "reverted": "projects" in reverted,
                "before": fp(p["orig"]), "after": fp(p["new"]), "notes": []})
    return out


def payload(job_id: str) -> dict:
    j = JOBS[job_id]
    b, plan = j["built"], j["plan"]
    return {
        "job_id": job_id, "base": j["base"], "base_name": T.BASES[j["base"]]["name"], "base_reason": j.get("base_reason"),
        "provider": j["provider"], "ok": b.ok, "error": None if b.ok else b.log,
        "pages": b.pages, "heading_scaled": b.heading_scaled if b.ok else 0, "gap_issues": b.gap_issues if b.ok else [], "bottom": round(b.bottom), "fill_pct": round(100 * b.bottom / 745) if b.ok else 0,
        "warnings": plan["warnings"] + j["log"], "gaps": plan["gaps"], "keywords": plan["keywords"], "summary": plan["summary"],
        "slots": slots_view(plan, j["reverted"]), "ats": T.ats_for(j["base"], plan, b, j["jd"], j["reverted"]), "v": int(time.time() * 1000),
        "meta": jdmod.extract_meta(j["jd"], j.get("url", "")),
        "timings": j.get("timings"),
    }


@app.post("/api/fetch-jd")
def fetch_jd(req: FetchReq):
    try:
        return jdmod.fetch_jd(req.url)
    except jdmod.JDError as e:
        raise HTTPException(422, str(e))


@app.post("/api/jd-meta")
def jd_meta(req: MetaReq):
    """Company and role guessed from pasted job text, so the tracker boxes fill themselves."""
    return jdmod.extract_meta(req.text, req.url)


@app.post("/api/generate")
def generate(req: GenReq):
    if req.base not in ("auto", *T.BASES):
        raise HTTPException(400, "unknown base resume")
    if len(req.jd.strip()) < 80:
        raise HTTPException(400, "The job description is too short.")
    job_id = uuid.uuid4().hex[:10]
    provider = PROVIDER_OVERRIDE or T.get_provider(req.mock)
    try:
        r = T.generate(req.base, req.jd, OUT / job_id, provider)
    except Exception as e:  # API errors, etc.
        raise HTTPException(502, f"{type(e).__name__}: {e}")
    r["url"] = req.url
    JOBS[job_id] = r
    return payload(job_id)


def _entry_view(e: dict) -> dict:
    return dict(e)


def _update(job_id: str, **kw) -> None:
    with QLOCK:
        QUEUE[job_id].update(kw)


def _guess_label(jd: str, url: str) -> tuple[str, str, str]:
    """Company, role and a short label for the queue row, from whatever text or link we have right now."""
    try:
        m = jdmod.extract_meta(jd, url) if (jd.strip() or url.strip()) else {"company": "", "role": ""}
    except Exception:
        m = {"company": "", "role": ""}
    company, role = m.get("company") or "", m.get("role") or ""
    label = ": ".join(x for x in (company, role) if x) or (url.strip()[:70] if url.strip() else (jd.strip().splitlines() or [""])[0][:70]) or "Job"
    return company, role, label


def _run_job(job_id: str, jd: str, url: str, base: str, mock: bool) -> None:
    _update(job_id, status="running", started=time.time())
    try:
        if not jd.strip():  # a link only: fetch it here so many links fetch in parallel too
            f = jdmod.fetch_jd(url)
            jd = (f["title"] + (" at " + f["company"] if f.get("company") else "") + "\n\n" if f.get("title") else "") + f["text"]
            url = f.get("url") or url
        if len(jd.strip()) < 80:
            raise ValueError("The job description is too short.")
        provider = PROVIDER_OVERRIDE or T.get_provider(mock)
        r = T.generate(base, jd, OUT / job_id, provider)
        r["url"] = url
        JOBS[job_id] = r
        b = r["built"]
        meta = jdmod.extract_meta(jd, url)
        company, role = meta.get("company") or "", meta.get("role") or ""
        _update(job_id, status="done" if b.ok else "failed", finished=time.time(), company=company, role=role,
                label=": ".join(x for x in (company, role) if x) or QUEUE[job_id]["label"], base=r["base"], base_name=T.BASES[r["base"]]["name"],
                ok=b.ok, pages=b.pages, fill_pct=round(100 * b.bottom / 745) if b.ok else 0, timings=r.get("timings"),
                error=None if b.ok else (b.log or "LaTeX failed")[-300:],
                pdf_url=f"/api/pdf/{job_id}?download=true&company={quote(company)}" if b.ok else None)
    except jdmod.JDError as e:
        _update(job_id, status="error", finished=time.time(), error=str(e))
    except Exception as e:  # API errors, timeouts, etc. One bad job never stops the rest of the queue
        _update(job_id, status="error", finished=time.time(), error=f"{type(e).__name__}: {e}"[:400])


@app.post("/api/batch")
def batch(req: BatchReq):
    if not req.items:
        raise HTTPException(400, "Nothing to queue.")
    if len(req.items) > MAX_BATCH:
        raise HTTPException(400, f"At most {MAX_BATCH} jobs at a time.")
    for it in req.items:
        if it.base not in ("auto", *T.BASES):
            raise HTTPException(400, "unknown base resume")
        if len(it.jd.strip()) < 80 and not it.url.strip():
            raise HTTPException(400, "Each job needs a link or at least a few sentences of job text.")
    out = []
    for it in req.items:
        job_id = uuid.uuid4().hex[:10]
        company, role, label = _guess_label(it.jd, it.url)
        entry = {"id": job_id, "status": "queued", "label": label, "company": company, "role": role, "url": it.url.strip(), "requested_base": it.base,
                 "base": None, "base_name": None, "created": time.time(), "started": None, "finished": None, "error": None,
                 "ok": None, "pages": None, "fill_pct": None, "pdf_url": None, "timings": None, "tracked": False}
        with QLOCK:
            QUEUE[job_id] = entry
            FUTURES[job_id] = EXEC.submit(_run_job, job_id, it.jd, it.url.strip(), it.base, req.mock)
        out.append(_entry_view(entry))
    return {"jobs": out, "workers": WORKERS}


@app.get("/api/jobs")
def jobs():
    with QLOCK:
        return {"jobs": [_entry_view(e) for e in QUEUE.values()], "workers": WORKERS, "now": time.time()}


@app.get("/api/jobs/{job_id}")
def job_result(job_id: str):
    """The full review payload for a finished queue job (same shape /api/generate returns)."""
    if job_id not in QUEUE:
        raise HTTPException(404, "unknown job")
    if job_id not in JOBS:
        raise HTTPException(409, "not finished yet")
    return payload(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    with QLOCK:
        e, fut = QUEUE.get(job_id), FUTURES.get(job_id)
        if not e:
            raise HTTPException(404, "unknown job")
        if e["status"] == "queued" and fut is not None and fut.cancel():
            e.update(status="cancelled", finished=time.time())
        return _entry_view(e)


@app.post("/api/jobs/clear")
def jobs_clear():
    """Forget finished, failed and cancelled rows (the resumes stay available if you still have them open)."""
    with QLOCK:
        for k in [k for k, e in QUEUE.items() if e["status"] in ("done", "failed", "error", "cancelled")]:
            QUEUE.pop(k, None); FUTURES.pop(k, None)
        return {"jobs": [_entry_view(e) for e in QUEUE.values()]}


@app.post("/api/revert")
def revert(req: RevertReq):
    j = JOBS.get(req.job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    j["reverted"] = set(req.reverted)
    j["built"] = T.rebuild(j["base"], j["plan"], OUT / req.job_id, j["reverted"])
    if j["built"].ok and j["built"].pages > 1:
        j["log"] = j["log"] + ["With those edits the resume runs to 2 pages."]
    return payload(req.job_id)


def download_name(company: str, ext: str) -> str:
    """Dhana_Karthikeya_Ventrapragada_Resume_<Company>.<ext>, the same naming as the hosted resumes."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_")[:50]
    return "Dhana_Karthikeya_Ventrapragada_Resume" + (f"_{slug}" if slug else "") + f".{ext}"


@app.get("/api/pdf/{job_id}")
def pdf(job_id: str, download: bool = False, company: str = ""):
    j = JOBS.get(job_id)
    if not j or not j["built"].ok:
        raise HTTPException(404, "no pdf")
    return FileResponse(j["built"].pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'{"attachment" if download else "inline"}; filename="{download_name(company, "pdf")}"'})


@app.get("/api/tex/{job_id}")
def tex(job_id: str, company: str = ""):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "no tex")
    return FileResponse(OUT / job_id / "resume.tex", media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{download_name(company, "tex")}"'})


class TrackReq(BaseModel):
    job_id: str
    company: str
    role: str


@app.post("/api/track")
def track(req: TrackReq):
    j = JOBS.get(req.job_id)
    if not j or not j["built"].ok:
        raise HTTPException(404, "Generate a resume first.")
    company, role = req.company.strip(), req.role.strip()
    if not company or not role:  # safety net: never log a blank, fill it from the job text
        m = jdmod.extract_meta(j["jd"], j.get("url", ""))
        company, role = company or m["company"], role or m["role"]
    try:
        res = tracker.log_application(j["built"].pdf, OUT / req.job_id / "resume.tex", company, role)
        with QLOCK:  # the queue row shows a "Tracked" tag, whether it was added from the row or from the tracker bar
            if req.job_id in QUEUE:
                QUEUE[req.job_id].update(tracked=True, company=res.get("company") or company, role=res.get("role") or role)
        return res
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Could not log to Google ({type(e).__name__}: {e}). A local copy was saved in applications/Resumes.")


@app.get("/api/status")
def status():
    import os
    return {"tracker": "google" if tracker.google_ready() else "local", "sheet_url": tracker.SHEET_URL, "folder_url": tracker.FOLDER_URL, "api_key": T.provider_kind() != "none", "provider": T.provider_kind(), "latex": bool(T._engine()), "workers": WORKERS, "bases": {k: v["name"] for k, v in T.BASES.items()}, "base_info": {k: {"name": v["name"], "blurb": v.get("blurb", "")} for k, v in T.BASES.items()}}


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
