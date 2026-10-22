"""Application tracker: Google Sheet (via an Apps Script web app) with a local fallback.

Sheet columns: Company | Role | Resume. The PDF you submitted goes into the "Resumes" subfolder.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
from pathlib import Path

from jd import clean_role

ROOT = Path(__file__).parent
SHEET_ID = os.environ.get("TRACKER_SHEET_ID", "10_DQh2vbybANN7uFN_-xjEs0x06-4DwNaPjoeUTjZvc")
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
FOLDER_URL = "https://drive.google.com/drive/folders/1q62Sj3Zc246RXvgxXlU8xR8jl6m_SXpV"
HEADERS = ["Company", "Role", "Resume"]
LOCAL_DIR = ROOT / "applications"


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ._&+-]+", "", s).strip()[:70] or "x"


def webhook_cfg() -> dict | None:
    import json

    cfg = {}
    f = ROOT / "tracker_config.json"
    if f.exists():
        try:
            cfg = json.loads(f.read_text())
        except Exception:
            cfg = {}
    url = os.environ.get("TRACKER_WEBHOOK_URL") or cfg.get("webhook_url", "")
    token = os.environ.get("TRACKER_TOKEN") or cfg.get("token", "")
    if url.startswith("https://script.google.com/") or url.startswith("http://127.0.0.1"):
        return {"url": url, "token": token}
    return None


def google_ready() -> bool:
    return webhook_cfg() is not None


def log_application(pdf: Path, tex: Path, company: str, role: str) -> dict:
    company = company.strip()
    role = clean_role(role, company)
    if not company or not role:
        raise ValueError("Company and role are required.")
    stem = f"{safe(company)} - {safe(role)}"
    # local copy of exactly what was submitted, in a Resumes subfolder
    res_dir = LOCAL_DIR / "Resumes"
    res_dir.mkdir(parents=True, exist_ok=True)
    local_pdf = res_dir / f"{stem}.pdf"
    shutil.copy(pdf, local_pdf)
    shutil.copy(tex, res_dir / f"{stem}.tex")
    out = {"mode": "local", "job": f"{company} - {role}", "company": company, "role": role, "local_pdf": str(local_pdf)}

    wh = webhook_cfg()
    if wh:
        import base64

        import httpx

        payload = {"token": wh["token"], "company": company, "role": role, "filename": f"{stem}.pdf",
                   "pdf_base64": base64.b64encode(Path(pdf).read_bytes()).decode()}
        r = httpx.post(wh["url"], json=payload, timeout=90, follow_redirects=True)
        try:
            d = r.json()
        except Exception:
            raise RuntimeError("The Apps Script did not return JSON. Re-deploy it as a web app with access set to Anyone.")
        if not d.get("ok"):
            raise RuntimeError("Tracker script said: " + str(d.get("error")))
        out.update(mode="google", drive_url=d["drive_url"], sheet_url=SHEET_URL, folder_url=FOLDER_URL)
    else:
        csv_path = LOCAL_DIR / "tracker.csv"
        new = not csv_path.exists()
        with open(csv_path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(HEADERS)
            w.writerow([company, role, f"Resumes/{local_pdf.name}"])
        out["csv"] = str(csv_path)
    return out
