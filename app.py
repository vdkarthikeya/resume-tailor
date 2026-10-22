"""Local resume tailor. Run: uvicorn app:app --port 8000"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

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


class FetchReq(BaseModel):
    url: str


class GenReq(BaseModel):
    base: str = "auto"
    jd: str
    mock: bool = False


class RevertReq(BaseModel):
    job_id: str
    reverted: list[str] = []


def slots_view(plan: dict, reverted: set[str]) -> list[dict]:
    out = []
    for k, e in plan["entries"].items():
        sid = f"entry:{k}"
        changed = [b["markup"] for b in e["new"]] != e["orig"]
        out.append({"id": sid, "group": "Experience & Leadership", "label": e["label"], "changed": changed, "reverted": sid in reverted,
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
        "pages": b.pages, "bottom": round(b.bottom), "fill_pct": round(100 * b.bottom / 772) if b.ok else 0,
        "warnings": plan["warnings"] + j["log"], "gaps": plan["gaps"], "keywords": plan["keywords"], "summary": plan["summary"],
        "slots": slots_view(plan, j["reverted"]), "ats": T.ats_for(j["base"], plan, b, j["jd"], j["reverted"]), "v": int(time.time() * 1000),
    }


@app.post("/api/fetch-jd")
def fetch_jd(req: FetchReq):
    try:
        return jdmod.fetch_jd(req.url)
    except jdmod.JDError as e:
        raise HTTPException(422, str(e))


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
    JOBS[job_id] = r
    return payload(job_id)


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


@app.get("/api/pdf/{job_id}")
def pdf(job_id: str, download: bool = False):
    j = JOBS.get(job_id)
    if not j or not j["built"].ok:
        raise HTTPException(404, "no pdf")
    return FileResponse(j["built"].pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'{"attachment" if download else "inline"}; filename="Karthik_Ventrapragada_Resume.pdf"'})


@app.get("/api/tex/{job_id}")
def tex(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "no tex")
    return FileResponse(OUT / job_id / "resume.tex", media_type="text/plain", headers={"Content-Disposition": 'attachment; filename="resume.tex"'})


class TrackReq(BaseModel):
    job_id: str
    company: str
    role: str


@app.post("/api/track")
def track(req: TrackReq):
    j = JOBS.get(req.job_id)
    if not j or not j["built"].ok:
        raise HTTPException(404, "Generate a resume first.")
    try:
        return tracker.log_application(j["built"].pdf, OUT / req.job_id / "resume.tex", req.company, req.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Could not log to Google ({type(e).__name__}: {e}). A local copy was saved in applications/Resumes.")


@app.get("/api/status")
def status():
    import os
    return {"tracker": "google" if tracker.google_ready() else "local", "sheet_url": tracker.SHEET_URL, "folder_url": tracker.FOLDER_URL, "api_key": T.provider_kind() != "none", "provider": T.provider_kind(), "latex": bool(T._engine()), "bases": {k: v["name"] for k, v in T.BASES.items()}}


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
