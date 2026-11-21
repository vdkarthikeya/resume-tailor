"""Consistency check across the places a resume change has to land.

    python scripts/sync_check.py                     # repo only
    python scripts/sync_check.py --site ../site      # also the website repo (vdkarthikeya.github.io clone)

Exit code 1 if anything disagrees. The Claude Doc "Master Doc: Everything I've Done" cannot be read from here, so master_doc.md
(its synced copy) stands in for it. Used by tests/test_all.py (repo part) so a drift fails the test run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BANNED = [(re.compile(r"built with claude", re.I), "'Built with Claude'"), (re.compile("[\u2013\u2014]"), "an en or em dash"),
          (re.compile(r"\bin progress\b", re.I), "'in progress'")]
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def master_text(root: Path) -> str:
    return (root / "master_doc.md").read_text()


def tex_projects(tex: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\\resumeProjectHeading\s*\{\s*\\textbf\{([^}]*)\}", tex)]


def check_repo(root: Path = ROOT) -> list[str]:
    bad: list[str] = []
    master = master_text(root)
    mnorm = _norm(master)
    bank = json.loads((root / "bank/projects.json").read_text())
    titles = {_norm(p["title"]): p for p in bank}

    for p in bank:
        for b in p["bullets"]:
            for n in NUM.findall(b["markup"].replace("**", "")):
                if n.rstrip("%") not in master and n not in master:
                    bad.append(f"bank {b['id']}: number {n} is not in master_doc.md")
            for rx, name in BANNED:
                if rx.search(b["markup"]):
                    bad.append(f"bank {b['id']}: contains {name}")
        for tool in p["stack"]:
            if tool.lower() not in master.lower():
                bad.append(f"bank {p['id']}: tool {tool} is not in master_doc.md")
        first = " ".join(_norm(p["title"]).split()[:2])
        if first not in mnorm:
            bad.append(f"bank {p['id']}: '{p['title']}' is not mentioned in master_doc.md")

    for f in sorted((root / "resumes").glob("*.tex")):
        tex = f.read_text()
        for t in tex_projects(tex):
            if not any(_norm(t) == k or k.startswith(_norm(t) + " ") or _norm(t).startswith(k + " ") for k in titles):
                bad.append(f"{f.name}: project '{t}' has no entry in bank/projects.json")
        for rx, name in BANNED:
            if rx.search(re.sub(r"%.*", "", tex)):
                bad.append(f"{f.name}: contains {name}")

    return bad


def check_site(root: Path, site: Path) -> list[str]:
    bad: list[str] = []
    mnorm = _norm(master_text(root))
    for k in ("ds", "ml", "pm", "swe"):
        a, b = root / f"resumes/{k}.tex", site / f"resumes/src/resume_{k}.tex"
        if not b.exists():
            bad.append(f"site: resumes/src/resume_{k}.tex is missing")
        elif a.read_text().strip() != b.read_text().strip():
            bad.append(f"site: resumes/src/resume_{k}.tex differs from the repo's resumes/{k}.tex (rebuild and copy)")
        pdf = site / f"resumes/Dhana_Karthikeya_Ventrapragada_Resume_{k.upper()}.pdf"
        if not pdf.exists():
            bad.append(f"site: {pdf.name} is missing")
        else:
            try:
                import pymupdf
                text = "\n".join(pg.get_text() for pg in pymupdf.open(pdf))
                for t in tex_projects(a.read_text()):
                    if t not in text:
                        bad.append(f"site: {pdf.name} does not show project '{t}' that resumes/{k}.tex has")
            except ImportError:
                pass
    data = site / "data.js"
    if data.exists():
        d = data.read_text()
        for m in re.finditer(r'"title":\s*"([^"]+)"', d[d.find('"projects"'):] if '"projects"' in d else ""):
            first = " ".join(_norm(m.group(1)).split()[:2])
            if first and first not in mnorm:
                bad.append(f"site data.js: project '{m.group(1)}' is not in master_doc.md")
        for rx, name in BANNED[:1] + BANNED[1:2]:
            if rx.search(d):
                bad.append(f"site data.js: contains {name}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, help="a clone of vdkarthikeya.github.io")
    a = ap.parse_args()
    bad = check_repo()
    if a.site:
        bad += check_site(ROOT, a.site)
    for b in bad:
        print("-", b)
    print("OK, all places agree" if not bad else f"{len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
