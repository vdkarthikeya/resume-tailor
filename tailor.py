"""Tailor one of the base resumes to a job description.

The model never writes LaTeX. It returns plain-text edits for fixed slots
(bullets, skills lines, coursework, project picks). Every edit is validated
against the Master Doc before it is rendered into the untouched template.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ats as ATS
import tex_slots as T

ROOT = Path(__file__).parent
BASES = {
    "ds": dict(file="resumes/ds.tex", name="Data Science", blurb="IDX Exchange first, data and modeling focus"),
    "ml": dict(file="resumes/ml.tex", name="Machine Learning", blurb="Gemini pipeline, XGBoost, SightLine"),
    "swe": dict(file="resumes/swe.tex", name="Software Engineering", blurb="Guang Labs first, FastAPI, React, Auth0"),
    "pm": dict(file="resumes/pm.tex", name="Product / Program Management", blurb="After Collective first, product and coordination work"),
}
# Entries whose bullets are never rewritten, only kept in place (user asked for the CS 61A bullet to stay as written).
LOCKED_ENTRY_MARKERS = ("CS 61A",)


def is_locked_entry(e) -> bool:
    return any(mk in f"{e.company} {e.role}" for mk in LOCKED_ENTRY_MARKERS)


BASES = {k: v for k, v in BASES.items() if (ROOT / v["file"]).exists()}
PAGE_BOTTOM_TARGET = 745.0  # originals end near 772; below this the page looks under-filled
PAGE_BOTTOM_MAX = 785.0
SKILL_LINE_MAX_CHARS = 110
MAX_PROJECTS = 3  # more projects means fewer bullets each; three projects keep room for 2-3 strong bullets apiece
MAX_PROJECT_BULLETS = 3

BANNED = [
    (r"gradescope|autograder", "mentions Gradescope/autograders (you asked to keep that off)"),
    (r"co-?found", "claims co-founding"),
    (r"\bran \d+ weekly|\bran four weekly", "uses 'ran' for the sections (you said 'taught')"),
    (r"\bleverag|\bspearhead|\bsynerg|\bpassionate\b|\bcutting-edge\b", "uses filler wording"),
]


# ---------------------------------------------------------------- text helpers
def norm_loose(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"[*`\\]", "", s)
    s = re.sub(r"[^a-z0-9% ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(s: str) -> set[str]:
    return {m.group(0).rstrip(",") for m in NUM_RE.finditer(s)}


def load_bank():
    projects = json.load(open(ROOT / "bank/projects.json"))
    courses = json.load(open(ROOT / "bank/courses.json"))
    return {p["id"]: p for p in projects}, courses


def load_master() -> str:
    return (ROOT / "master_doc.md").read_text()


@dataclass
class Ctx:
    master: str
    master_norm: str
    allowed_numbers: set
    bank: dict
    courses: dict


def make_ctx() -> Ctx:
    master = load_master()
    bank, courses = load_bank()
    nums = numbers_in(master)
    for k in BASES:
        nums |= numbers_in((ROOT / BASES[k]["file"]).read_text())
    for p in bank.values():
        for b in p["bullets"]:
            nums |= numbers_in(b["markup"])
    return Ctx(master, norm_loose(master), nums, bank, courses)


# ---------------------------------------------------------------- validation
def check_bullet_text(markup: str, ctx: Ctx, max_len: int) -> list[str]:
    errs = []
    try:
        T.markup_to_latex(markup)
    except T.MarkupError as e:
        errs.append(str(e))
        return errs
    plain_text = markup.replace("**", "")
    if len(plain_text) > max_len:
        errs.append(f"too long ({len(plain_text)} chars, limit {max_len})")
    for pat, why in BANNED:
        if re.search(pat, plain_text, re.I):
            errs.append(why)
    bad_nums = [n for n in numbers_in(plain_text) if n not in ctx.allowed_numbers]
    if bad_nums:
        errs.append("number(s) not found in your Master Doc or resumes: " + ", ".join(sorted(bad_nums)))
    return errs


def verify_sources(sources: list[str], ctx: Ctx) -> tuple[bool, list[dict]]:
    details = []
    for s in sources or []:
        n = norm_loose(s)
        found = len(n) >= 10 and n in ctx.master_norm
        details.append({"quote": s, "found": found})
    ok = bool(details) and all(d["found"] for d in details)
    return ok, details


def bank_id_for(pb, bank: dict) -> str | None:
    norm = lambda u: (u or "").rstrip("/").lower()
    for b in bank.values():
        if pb.url and norm(b["url"]) == norm(pb.url):
            return b["id"]
    return next((b["id"] for b in bank.values() if b["title"] == pb.title), None)


def plain_label(label: str) -> str:
    return label.replace("\\&", "&")


# ---------------------------------------------------------------- plan building
def build_plan(parsed: T.Parsed, proposal: dict, ctx: Ctx, base_key: str) -> dict:
    warnings: list[str] = []
    plan: dict = {"base": base_key, "entries": {}, "skills": {}, "warnings": warnings}

    # ---- entries (experience + leadership bullets)
    prop_entries = {e.get("entry_id"): e for e in proposal.get("entries", [])}
    for e in parsed.entries:
        orig = [b.markup for b in e.bullets]
        pe = prop_entries.get(e.id)
        res = {"label": f"{e.company}: {e.role}", "orig": orig, "new": [{"markup": m, "orig_idx": i, "kind": "same", "sources": []} for i, m in enumerate(orig)]}
        if pe is None or is_locked_entry(e):
            plan["entries"][e.id] = res
            continue
        pb = pe.get("bullets", [])
        if len(pb) != len(orig):
            warnings.append(f"{res['label']}: model returned {len(pb)} bullets instead of {len(orig)}; kept your original bullets.")
            plan["entries"][e.id] = res
            continue
        max_len = int(max(len(m.replace("**", "")) for m in orig) * 1.25) + 5
        used: set[int] = set()
        new: list[dict | None] = []
        for pos, b in enumerate(pb):
            text = (b.get("text") or "").strip()
            fi = b.get("from_index")
            srcs = b.get("source") or []
            if isinstance(fi, int) and 0 <= fi < len(orig) and text == orig[fi] and fi not in used:
                used.add(fi)
                new.append({"markup": text, "orig_idx": fi, "kind": "same" if fi == pos else "moved", "sources": []})
                continue
            errs = check_bullet_text(text, ctx, max_len)
            ok, details = verify_sources(srcs, ctx)
            if not ok:
                errs.append("no verifiable source quote from the Master Doc")
            if errs:
                warnings.append(f"{res['label']}, bullet {pos+1}: edit rejected ({'; '.join(errs)}). Kept your original wording.")
                new.append(None)
                continue
            if isinstance(fi, int) and 0 <= fi < len(orig) and fi not in used:
                used.add(fi)
            new.append({"markup": text, "orig_idx": fi if isinstance(fi, int) else None, "kind": "rewrite" if isinstance(fi, int) else "new", "sources": details})
        # fill rejected slots with unused originals (keeps bullet count and facts safe)
        leftovers = [i for i in range(len(orig)) if i not in used]
        for pos, item in enumerate(new):
            if item is None:
                i = leftovers.pop(0)
                new[pos] = {"markup": orig[i], "orig_idx": i, "kind": "same" if i == pos else "moved", "sources": []}
        res["new"] = new
        plan["entries"][e.id] = res

    # ---- skills lines
    prop_skills = {plain_label(s.get("label", "")).lower(): s for s in proposal.get("skills", [])}
    master_l = ctx.master.lower()
    for sl in parsed.skills:
        label = plain_label(sl.label)
        res = {"label": label, "orig": sl.items, "new": sl.items, "kind": "same", "warning": None}
        ps = prop_skills.get(label.lower())
        if ps:
            items = [i.strip() for i in ps.get("items", []) if i.strip()]
            errs = []
            if not items:
                errs.append("empty")
            if len({i.lower() for i in items}) != len(items):
                errs.append("duplicate items")
            missing = [i for i in items if i.lower() not in master_l and i not in sl.items]
            if missing:
                errs.append("not in your Master Doc: " + ", ".join(missing))
            for i in items:
                try:
                    T.markup_to_latex(i)
                except T.MarkupError as ex:
                    errs.append(f"{i!r}: {ex}")
            if len(label) + 2 + len(", ".join(items)) > SKILL_LINE_MAX_CHARS:
                errs.append(f"line would wrap (over {SKILL_LINE_MAX_CHARS} chars)")
            if errs:
                warnings.append(f"Skills / {label}: edit rejected ({'; '.join(errs)}). Kept your original line.")
            elif items != sl.items:
                res["new"] = items
                res["kind"] = "reorder" if sorted(items) == sorted(sl.items) else "rewrite"
        plan["skills"][sl.id] = res

    # ---- coursework
    cw = parsed.coursework
    res = {"orig": {"completed": cw.completed, "in_progress": cw.in_progress}, "new": {"completed": cw.completed, "in_progress": cw.in_progress}, "kind": "same"}
    pc = proposal.get("coursework")
    if pc:
        comp, prog = pc.get("completed", []), pc.get("in_progress", [])
        errs = []
        if any(c not in ctx.courses["completed"] for c in comp):
            errs.append("unknown completed course name")
        if any(c not in ctx.courses["in_progress"] for c in prog):
            errs.append("unknown in-progress course name")
        if len(comp) + len(prog) > len(cw.completed) + len(cw.in_progress):
            errs.append("more courses than your original (two-line cap)")
        if not comp:
            errs.append("no completed courses")
        if len(set(comp + prog)) != len(comp + prog):
            errs.append("duplicates")
        if errs:
            warnings.append(f"Coursework: edit rejected ({'; '.join(errs)}). Kept your original line.")
        elif (comp, prog) != (cw.completed, cw.in_progress):
            res["new"] = {"completed": comp, "in_progress": prog}
            res["kind"] = "rewrite"
    plan["coursework"] = res

    # ---- projects
    pr = parsed.projects
    orig_projects = []
    for pb in pr.projects:
        pid = bank_id_for(pb, ctx.bank)
        orig_projects.append({"id": pid, "title": pb.title, "url": pb.url, "tech": pb.tech, "style": pb.style, "bullets": [b.markup for b in pb.bullets]})
    default_style = orig_projects[0]["style"] if orig_projects else "link"
    pres = {"orig": orig_projects, "new": orig_projects, "kind": "same"}
    pp = proposal.get("projects")
    if pp:
        errs = []
        ids = [p.get("project_id") for p in pp]
        if len(pp) != len(orig_projects):
            errs.append(f"expected {len(orig_projects)} projects, got {len(pp)}")
        if len(pp) > MAX_PROJECTS:
            errs.append(f"at most {MAX_PROJECTS} projects allowed")
        if any(i not in ctx.bank for i in ids):
            errs.append("unknown project id")
        if len(set(ids)) != len(ids):
            errs.append("duplicate project")
        approved = {norm_loose(m) for p in ctx.bank.values() for m in (b["markup"] for b in p["bullets"])}
        approved |= {norm_loose(m) for p in orig_projects for m in p["bullets"]}
        built = []
        if not errs:
            max_len = int(max(len(m.replace("**", "")) for p in orig_projects for m in p["bullets"]) * 1.25) + 5
            total = 0
            for p in pp:
                bank = ctx.bank[p["project_id"]]
                same = next((o for o in orig_projects if o["id"] == bank["id"]), None)
                bl = []
                if not 1 <= len(p.get("bullets", [])) <= MAX_PROJECT_BULLETS:
                    errs.append(f"{bank['title']}: needs 1 to {MAX_PROJECT_BULLETS} bullets")
                    break
                for b in p["bullets"]:
                    text = (b.get("text") or "").strip()
                    if norm_loose(text) in approved and not check_bullet_text(text, ctx, 10_000):
                        bl.append({"markup": text, "kind": "approved", "sources": []})
                        continue
                    be = check_bullet_text(text, ctx, max_len)
                    ok, details = verify_sources(b.get("source") or [], ctx)
                    if not ok:
                        be.append("no verifiable source quote")
                    if be:
                        errs.append(f"{bank['title']}: {'; '.join(be)}")
                    bl.append({"markup": text, "kind": "new", "sources": details})
                total += len(bl)
                tech_items = p.get("tech")
                stack_l = {s.lower() for s in bank["stack"]}
                if tech_items:
                    if any(t.lower() not in stack_l for t in tech_items):
                        errs.append(f"{bank['title']}: tech outside its stack")
                else:
                    tech_items = None if same else bank["stack"][:3]
                if tech_items is not None:
                    tech = ", ".join(tech_items + ([bank["suffix"]] if bank["suffix"] else []))
                    try:
                        tech_latex = T.markup_to_latex(tech)
                    except T.MarkupError as ex:
                        errs.append(str(ex))
                        tech_latex = tech
                else:
                    tech_latex = same["tech"]
                built.append({"id": bank["id"], "title": same["title"] if same else bank["title"], "url": same["url"] if same else bank["url"],
                              "tech": tech_latex, "style": same["style"] if same else default_style, "bullets": bl})
            orig_total = sum(len(p["bullets"]) for p in orig_projects)
            if not errs and abs(total - orig_total) > 1:
                errs.append(f"{total} project bullets vs {orig_total} originally (page fit)")
        if errs:
            warnings.append("Projects: edit rejected (" + "; ".join(errs) + "). Kept your original projects.")
        else:
            changed = [(b["id"], [x["markup"] for x in b["bullets"]]) for b in built] != [(o["id"], o["bullets"]) for o in orig_projects]
            if changed:
                pres["new"] = [{"id": b["id"], "title": b["title"], "url": b["url"], "tech": b["tech"], "style": b["style"], "bullets": [x["markup"] for x in b["bullets"]], "detail": b["bullets"]} for b in built]
                pres["kind"] = "rewrite"
    plan["projects"] = pres
    plan["gaps"] = proposal.get("gaps", [])
    plan["keywords"] = proposal.get("keywords", [])
    plan["summary"] = proposal.get("summary", "")
    return plan


# ---------------------------------------------------------------- rendering
def slot_ids(plan: dict) -> list[str]:
    out = [f"entry:{k}" for k in plan["entries"]]
    out += list(plan["skills"].keys())
    out += ["course", "projects"]
    return out


def changed_slots(plan: dict) -> list[str]:
    out = []
    for k, e in plan["entries"].items():
        if [b["markup"] for b in e["new"]] != e["orig"]:
            out.append(f"entry:{k}")
    for k, s in plan["skills"].items():
        if s["new"] != s["orig"]:
            out.append(k)
    if plan["coursework"]["new"] != plan["coursework"]["orig"]:
        out.append("course")
    if plan["projects"]["new"] != plan["projects"]["orig"]:
        out.append("projects")
    return out


def render_tex(parsed: T.Parsed, plan: dict, reverted: set[str] | None = None) -> str:
    reverted = reverted or set()
    reps: list[tuple[int, int, str]] = []
    for e in parsed.entries:
        pe = plan["entries"][e.id]
        if f"entry:{e.id}" in reverted:
            continue
        for b, nb in zip(e.bullets, pe["new"]):
            if nb["markup"] != b.markup:
                reps.append((b.start, b.end, T.markup_to_latex(nb["markup"])))
    for sl in parsed.skills:
        ps = plan["skills"][sl.id]
        if sl.id in reverted or ps["new"] == ps["orig"]:
            continue
        reps.append((sl.start, sl.end, ", ".join(T._esc(i) for i in ps["new"])))
    cw = parsed.coursework
    pc = plan["coursework"]
    if "course" not in reverted and pc["new"] != pc["orig"]:
        reps.append((cw.start, cw.end, T.render_coursework(pc["new"]["completed"], pc["new"]["in_progress"])))
    pr = plan["projects"]
    if "projects" not in reverted and pr["new"] != pr["orig"]:
        projs = [{"title": p["title"], "url": p["url"], "tech": p["tech"], "style": p.get("style", "link"), "bullets_latex": [T.markup_to_latex(m) for m in p["bullets"]]} for p in pr["new"]]
        reps.append((parsed.projects.start, parsed.projects.end, T.render_projects(projs)))
    return T.apply_replacements(parsed.text, reps)


# ---------------------------------------------------------------- compile + measure
@dataclass
class Built:
    ok: bool
    pdf: Path | None
    pages: int
    bottom: float
    log: str
    skill_wrap: list[str]


def _engine() -> list[str] | None:
    if shutil.which("pdflatex"):
        return ["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error"]
    if shutil.which("tectonic"):
        return ["tectonic", "--untrusted"]
    return None


def compile_tex(tex: str, outdir: Path, name: str = "resume", skills_check: list[tuple[str, str]] | None = None) -> Built:
    import pymupdf

    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    eng = _engine()
    if not eng:
        return Built(False, None, 0, 0, "No LaTeX engine found. Install MacTeX (brew install --cask mactex-no-gui) or tectonic (brew install tectonic).", [])
    src = outdir / f"{name}.tex"
    if eng[0] == "tectonic":  # XeTeX has no pdfTeX primitives; text stays extractable without them
        tex = tex.replace("\\input{glyphtounicode}", "").replace("\\pdfgentounicode=1", "")
    src.write_text(tex)
    if eng[0] == "pdflatex":
        cmd = eng + [f"-output-directory={outdir}", str(src)]
    else:
        cmd = eng + ["--outdir", str(outdir), str(src)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=outdir)
    except subprocess.TimeoutExpired:
        return Built(False, None, 0, 0, "LaTeX timed out", [])
    pdf = outdir / f"{name}.pdf"
    if r.returncode != 0 or not pdf.exists():
        tail = (r.stdout or "")[-1500:] + (r.stderr or "")[-500:]
        return Built(False, None, 0, 0, tail, [])
    doc = pymupdf.open(pdf)
    pages = len(doc)
    first = doc[0]
    bottom = max((b[3] for b in first.get_text("blocks")), default=0.0)
    wrap = []
    if skills_check:
        lines = []
        for blk in first.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                lines.append("".join(s["text"] for s in ln["spans"]))
        for label, last_item in skills_check:
            hit = [ln for ln in lines if ln.strip().startswith(label)]
            if hit and last_item not in hit[0]:
                wrap.append(label)
    return Built(True, pdf, pages, bottom, "", wrap)


# ---------------------------------------------------------------- providers
SYSTEM = """You tailor a student's one-page resume to a job description.

HARD RULES
1. Use ONLY facts from the MASTER DOC. Never invent a skill, tool, number, outcome, title, or date. If the job asks for something the Master Doc does not support, do NOT add it; list it under "gaps" so the student can see the honest mismatch.
2. Every bullet you rewrite or add must carry "source": 1 to 3 verbatim snippets (10+ characters each) copied exactly from the MASTER DOC that support every fact in the bullet. Bullets are rejected without checkable quotes.
3. Numbers must already appear in the Master Doc or the original resume. Do not compute new ones.
4. Bullet format is the XYZ method: "Accomplished [X] as measured by [Y] by doing [Z]". X is the achievement, Y is a measurable result that is already in the Master Doc (a number, scale, percent, count of tests, sources, records), and Z is the method or tools used. Write it as natural plain English, not a fill-in template (for example "Cut a simpler model's error from **29%** to **15%** by engineering a school district feature"). If the Master Doc has no real metric for a bullet, use a concrete, checkable outcome instead (what it enabled, how many cases it handled). Never invent a number.
   Voice: plain, direct, short. Start with a strong action verb (Built, Developed, Engineered, Implemented, Designed, Taught). Bold (**...**) the numbers and the job's key technical terms that the bullet truly demonstrates, at most 3 per bullet. No em dashes, no en dashes, no "--", no filler (leveraged, spearheaded, passionate). Use ² for superscript 2 and × for times. Nothing else: no backslashes, braces, ^, ~ or backticks.
   ATS wording: when the student really did the thing, use the job's exact term (REST APIs, not "web endpoints"; spell out "machine learning" where the job says it). Never use a job term the student did not earn.
5. Facts to respect: CS 61A is "taught" sections (never "ran", never Gradescope or autograders). Guang Labs work is merged to main; say "merged" unless the Master Doc says otherwise. The classifier is a Gemini-based classification service, not a custom-trained LLM. IDX is a preprocessing and modeling pipeline. The CLIP ideas for SightLine are proposals the Master Doc marks as not built, so only mention them if the Master Doc says they were built. 200+ is the 61A class size, not a caseload. Fung Fellowship: only what is documented as done.
6. The CS 61A entry is locked: return its bullets unchanged (from_index, identical text). It already says the sections were taught in Python, Scheme, and SQL, reinforcing linked lists, trees, lists, and dictionaries. The CDSS 198 entry must keep saying the student runs exam reviews and writes practice worksheets for CS and data science classes. Keep each entry's bullet count exactly as given and each bullet within about 25% of the original length, so the resume stays one full page. Do not touch headings, dates, titles, or GPA.

ATS RULES (the resume must pass automated screening AND read well to a person)
A. Keywords: list the 8 to 15 hard-skill terms the job uses, exactly as written, in "keywords". Each one the Master Doc supports must appear verbatim in the Skills lines AND be shown in at least one bullet. The first Skills line should lead with the job's own languages and tools.
B. Parse safety: single column, no tables or icons, plain hyphens in dates ("Jun 2026 - Aug 2026"), standard section names (Education, Technical Skills, Experience, Projects, Leadership & Involvement), standard degree wording ("Bachelor of Arts"). Never change headings, dates, titles, or the degree line.
C. Spell out and abbreviate once where the job uses both ("machine learning", "natural language processing (NLP)") only if the student's work truly fits.
D. Pick the strongest evidence for THIS job: the experiences and projects whose bullets best match the job's must-haves go first. Cut a weak project before a weak bullet.
E. Never keyword-stuff: no white text, no repeated skill lists, no term the student did not earn.

HOW TO TAILOR
- Put the most job-relevant bullet first in each entry (reorder with from_index, text identical to the original).
- Rewrite bullets into XYZ form (see rule 4) whenever the Master Doc gives you a real Y (number, scale, count) or a concrete outcome, and use the job's exact keywords where they are true. Improve at least half of the experience and project bullets this way. Keep a bullet exactly as given (same text, from_index set) only when it already reads as XYZ or the Master Doc has nothing more to add.
- Evidence: every skill you list should be demonstrated in at least one bullet or project when the Master Doc supports it, so skills are shown, not just listed. Prefer skills that appear in the bullets.
- Skills: reorder so the job's keywords come first; drop low-value items to make room; only add items that appear in the Master Doc. Keep each line under 110 characters including its label.
- Projects: pick the same number of projects as the base resume (never more than 3) from the PROJECT BANK, most relevant to the job. Prefer the approved bullets (give bank_id and the exact text). Use 2 or 3 bullets per project (1 only when the bank has just one approved bullet).
- Product and program management jobs (pm base): lead with discovery and product work (The After Collective interviews and concepts, Hindsight's product role, SightLine's cross-team work), then cross-functional and documentation work. Hindsight is a product-and-vision contribution built with Claude, never a backend you wrote.
- Coursework: choose from ALLOWED COURSES only, no more courses than the base has.
- Return your answer by calling the tool."""

TAILOR_TOOL = {
    "name": "submit_tailored_resume",
    "description": "Submit the tailored resume edits.",
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {"type": "array", "items": {"type": "string"}, "description": "8 to 15 hard-skill keywords and tools exactly as written in the job description (languages, frameworks, concepts), most important first"},
            "summary": {"type": "string", "description": "One or two plain sentences on what you changed and why"},
            "gaps": {"type": "array", "items": {"type": "string"}, "description": "Job requirements the Master Doc does not support (not added)"},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string"},
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from_index": {"type": ["integer", "null"]},
                                    "text": {"type": "string"},
                                    "source": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["from_index", "text", "source"],
                            },
                        },
                    },
                    "required": ["entry_id", "bullets"],
                },
            },
            "skills": {
                "type": "array",
                "items": {"type": "object", "properties": {"label": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}, "required": ["label", "items"]},
            },
            "coursework": {
                "type": "object",
                "properties": {"completed": {"type": "array", "items": {"type": "string"}}, "in_progress": {"type": "array", "items": {"type": "string"}}},
                "required": ["completed", "in_progress"],
            },
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                        "tech": {"type": ["array", "null"], "items": {"type": "string"}},
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"bank_id": {"type": ["string", "null"]}, "text": {"type": "string"}, "source": {"type": "array", "items": {"type": "string"}}},
                                "required": ["text", "source"],
                            },
                        },
                    },
                    "required": ["project_id", "bullets"],
                },
            },
        },
        "required": ["keywords", "summary", "gaps", "entries", "skills", "coursework", "projects"],
    },
}

PICK_TOOL = {
    "name": "pick_base_resume",
    "description": "Pick which base resume fits the job best.",
    "input_schema": {
        "type": "object",
        "properties": {"base": {"type": "string", "enum": ["ds", "ml", "swe", "pm"]}, "reason": {"type": "string"}},
        "required": ["base", "reason"],
    },
}


def describe_base(parsed: T.Parsed, ctx: Ctx) -> dict:
    return {
        "entries": [
            {"entry_id": e.id, "company": e.company, "role": e.role, "bullets": [{"index": i, "text": b.markup} for i, b in enumerate(e.bullets)]}
            for e in parsed.entries
        ],
        "skills": [{"label": plain_label(s.label), "items": s.items} for s in parsed.skills],
        "coursework": {"completed": parsed.coursework.completed, "in_progress": parsed.coursework.in_progress},
        "current_projects": [
            {"project_id": bank_id_for(pb, ctx.bank), "bullets": [b.markup for b in pb.bullets]} for pb in parsed.projects.projects
        ],
        "project_count_required": len(parsed.projects.projects),
    }


def build_user_prompt(parsed: T.Parsed, ctx: Ctx, jd: str, feedback: str | None = None) -> str:
    bank = [
        {"project_id": p["id"], "title": p["title"], "stack": p["stack"], "approved_bullets": [{"bank_id": b["id"], "text": b["markup"]} for b in p["bullets"]]}
        for p in ctx.bank.values()
    ]
    parts = [
        "## JOB DESCRIPTION\n" + jd.strip()[:12000],
        "## BASE RESUME (editable slots)\n" + json.dumps(describe_base(parsed, ctx), indent=1, ensure_ascii=False),
        "## PROJECT BANK\n" + json.dumps(bank, indent=1, ensure_ascii=False),
        "## ALLOWED COURSES\n" + json.dumps(ctx.courses, indent=1),
        "## MASTER DOC (the only source of facts)\n" + ctx.master,
    ]
    if feedback:
        parts.append("## FEEDBACK ON YOUR LAST ATTEMPT (fix these)\n" + feedback)
    return "\n\n".join(parts)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("RESUME_MODEL", "claude-sonnet-5-5")

    def _call(self, system: str, user: str, tool: dict) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
        )
        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise RuntimeError("model returned no tool call")

    def pick_base(self, jd: str) -> dict:
        sys = "Pick the base resume that best fits the job. ds = data scientist / analyst / analytics. ml = machine learning engineer / applied ML / research engineering. swe = software engineer / backend / full-stack / data engineer. pm = product manager / program manager / technical program manager / project coordination."
        return self._call(sys, "## JOB DESCRIPTION\n" + jd.strip()[:8000], PICK_TOOL)

    def tailor(self, parsed, ctx, jd, feedback=None) -> dict:
        return self._call(SYSTEM, build_user_prompt(parsed, ctx, jd, feedback), TAILOR_TOOL)


class ClaudeCodeProvider:
    """Uses the `claude` CLI (Claude Code) in headless mode, so it runs on your Claude subscription, no API key."""

    name = "claude-code"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("RESUME_CLAUDE_MODEL")  # e.g. sonnet, opus

    def _call(self, system: str, user: str, tool: dict) -> dict:
        cmd = ["claude", "-p", "--output-format", "json", "--json-schema", json.dumps(tool["input_schema"]),
               "--system-prompt", system, "--no-session-persistence", "--tools", ""]
        if self.model:
            cmd += ["--model", self.model]
        with tempfile.TemporaryDirectory() as td:  # empty cwd so no project files or CLAUDE.md leak in
            try:
                r = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=420, cwd=td)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Claude Code timed out")
        try:
            d = json.loads(r.stdout)
        except Exception:
            raise RuntimeError("Claude Code failed: " + ((r.stderr or r.stdout or "no output")[-400:]))
        if d.get("is_error"):
            raise RuntimeError("Claude Code error: " + str(d.get("result"))[:400])
        out = d.get("structured_output")
        if not out:
            try:
                out = json.loads(d.get("result", ""))
            except Exception:
                raise RuntimeError("Claude Code returned no structured output")
        return out

    def pick_base(self, jd: str) -> dict:
        sys = "Pick the base resume that best fits the job. ds = data scientist / analyst / analytics. ml = machine learning engineer / applied ML / research engineering. swe = software engineer / backend / full-stack / data engineer. pm = product manager / program manager / technical program manager / project coordination."
        return self._call(sys, "## JOB DESCRIPTION\n" + jd.strip()[:8000], PICK_TOOL)

    def tailor(self, parsed, ctx, jd, feedback=None) -> dict:
        return self._call(SYSTEM, build_user_prompt(parsed, ctx, jd, feedback), TAILOR_TOOL)


KEYWORDS = {
    "swe": ["backend", "back-end", "full-stack", "full stack", "frontend", "react", "typescript", "api", "microservice", "distributed", "software engineer", "devops", "aws", "docker", "kubernetes", "java", "rest"],
    "ml": ["machine learning", "deep learning", "pytorch", "tensorflow", "llm", "nlp", "computer vision", "inference", "embedding", "mlops", "model", "neural", "ml engineer", "transformer"],
    "pm": ["product manager", "program manager", "tpm", "roadmap", "stakeholder", "cross-functional", "product requirements", "user research", "project management"],
    "ds": ["data scientist", "analytics", "analyst", "sql", "statistics", "experiment", "a/b", "dashboard", "tableau", "forecast", "business intelligence", "insights", "regression"],
}


class MockProvider:
    """No API key: picks a base by keyword count and only reorders skills."""

    name = "mock"

    def pick_base(self, jd: str) -> dict:
        low = jd.lower()
        score = {k: sum(low.count(w) for w in ws) for k, ws in KEYWORDS.items()}
        best = max(score, key=score.get)
        return {"base": best, "reason": f"keyword counts {score} (mock mode, no API key)"}

    def tailor(self, parsed, ctx, jd, feedback=None) -> dict:
        low = jd.lower()
        skills = []
        for s in parsed.skills:
            items = sorted(s.items, key=lambda i: (0 if i.lower() in low else 1))
            skills.append({"label": plain_label(s.label), "items": items})
        entries = [
            {"entry_id": e.id, "bullets": [{"from_index": i, "text": b.markup, "source": []} for i, b in enumerate(e.bullets)]} for e in parsed.entries
        ]
        projects = []
        for pb in parsed.projects.projects:
            pid = bank_id_for(pb, ctx.bank)
            projects.append({"project_id": pid, "tech": None, "bullets": [{"bank_id": None, "text": b.markup, "source": []} for b in pb.bullets]})
        return {
            "keywords": [],
            "summary": "Mock mode (no ANTHROPIC_API_KEY): only reordered skills that match the job text.",
            "gaps": [],
            "entries": entries,
            "skills": skills,
            "coursework": {"completed": parsed.coursework.completed, "in_progress": parsed.coursework.in_progress},
            "projects": projects,
        }


def get_provider(force_mock: bool = False):
    if force_mock:
        return MockProvider()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if shutil.which("claude"):
        return ClaudeCodeProvider()
    return MockProvider()


def provider_kind() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    return "claude-code" if shutil.which("claude") else "none"


# ---------------------------------------------------------------- orchestration
def skills_check_pairs(parsed: T.Parsed, plan: dict, reverted: set[str]) -> list[tuple[str, str]]:
    out = []
    for sl in parsed.skills:
        ps = plan["skills"][sl.id]
        items = ps["orig"] if sl.id in reverted else ps["new"]
        out.append((plain_label(sl.label), items[-1]))
    return out


def feedback_text(plan: dict, built: Built) -> str | None:
    msgs = list(plan["warnings"])
    if built.ok and built.pages > 1:
        msgs.append("The resume overflowed to 2 pages. Shorten rewritten bullets or drop low-value skills so it fits on ONE page.")
    elif built.ok and built.bottom < PAGE_BOTTOM_TARGET:
        msgs.append(f"The page is under-filled (text ends at {built.bottom:.0f} of ~772 points). Keep more detail, using only Master Doc facts.")
    if built.ok and built.skill_wrap:
        msgs.append("These skills lines wrap onto two lines, shorten them: " + ", ".join(built.skill_wrap))
    return "\n".join(f"- {m}" for m in msgs) if msgs else None


def revert_to_fit(parsed: T.Parsed, plan: dict, outdir: Path, reverted: set[str], built: Built, log: list[str]) -> tuple[Built, set[str]]:
    """Greedy safety net: revert the changed slots that grew the most until it fits on one page."""

    def growth(sid: str) -> int:
        if sid.startswith("entry:"):
            e = plan["entries"][sid.split(":", 1)[1]]
            return sum(len(b["markup"]) for b in e["new"]) - sum(len(m) for m in e["orig"])
        if sid.startswith("skills:"):
            s = plan["skills"][sid]
            return len(", ".join(s["new"])) - len(", ".join(s["orig"]))
        if sid == "course":
            n, o = plan["coursework"]["new"], plan["coursework"]["orig"]
            return len(", ".join(n["completed"] + n["in_progress"])) - len(", ".join(o["completed"] + o["in_progress"]))
        pr = plan["projects"]
        return sum(len(m) for p in pr["new"] for m in p["bullets"]) - sum(len(m) for p in pr["orig"] for m in p["bullets"])

    cand = sorted([s for s in changed_slots(plan) if s not in reverted], key=growth, reverse=True)
    while built.ok and built.pages > 1 and cand:
        sid = cand.pop(0)
        reverted = reverted | {sid}
        log.append(f"Reverted '{sid}' to your original to keep the resume on one page.")
        built = compile_tex(render_tex(parsed, plan, reverted), outdir, "resume", skills_check_pairs(parsed, plan, reverted))
    return built, reverted


def generate(base_key: str, jd: str, outdir: Path, provider=None, max_attempts: int = 3) -> dict:
    provider = provider or get_provider()
    ctx = make_ctx()
    reason = None
    if base_key == "auto":
        pick = provider.pick_base(jd)
        base_key, reason = pick["base"], pick["reason"]
        if base_key not in BASES:
            base_key = "swe" if "swe" in BASES else next(iter(BASES))
    parsed = T.parse((ROOT / BASES[base_key]["file"]).read_text())
    feedback = None
    plan = built = None
    reverted: set[str] = set()
    log: list[str] = []
    for attempt in range(max_attempts):
        proposal = provider.tailor(parsed, ctx, jd, feedback)
        plan = build_plan(parsed, proposal, ctx, base_key)
        tex = render_tex(parsed, plan, set())
        built = compile_tex(tex, outdir, "resume", skills_check_pairs(parsed, plan, set()))
        if not built.ok:
            feedback = "LaTeX failed to compile: " + built.log[-600:]
            continue
        feedback = feedback_text(plan, built)
        rep = ats_for(base_key, plan, built, jd, set())
        ats_retry = False
        if rep and attempt == 0 and len(rep["missing_supported"]) >= 3 and not isinstance(provider, MockProvider):
            ats_retry = True
            note = ("These job keywords ARE supported by the Master Doc but are missing from the resume text, so ATS keyword search would miss them: "
                    + ", ".join(rep["missing_supported"][:10]) + ". Work them in where true, using the job's exact wording (skills line or bullets).")
            feedback = (feedback + "\n- " + note) if feedback else "- " + note
        # only retry for problems the model can fix; rejected edits are already safely reverted
        retry_needed = built.pages > 1 or built.bottom < PAGE_BOTTOM_TARGET or built.skill_wrap or ats_retry
        if not retry_needed or isinstance(provider, MockProvider):
            break
    if built and built.ok and built.pages > 1:
        built, reverted = revert_to_fit(parsed, plan, outdir, reverted, built, log)
    return {"jd": jd, "base": base_key, "base_reason": reason, "plan": plan, "built": built, "reverted": reverted, "log": log, "parsed": parsed, "provider": provider.name}


def ats_for(base_key: str, plan: dict, built: "Built", jd: str, reverted: set[str]) -> dict | None:
    if not built.ok:
        return None
    base_tex = (ROOT / BASES[base_key]["file"]).read_text()
    parsed0 = T.parse(base_tex)
    final_tex = render_tex(parsed0, plan, reverted)
    p2 = T.parse(final_tex)
    bullets = [b.markup or b.latex for e in p2.entries for b in e.bullets] + [b.markup or b.latex for pb in p2.projects.projects for b in pb.bullets]
    skills = [i for sl in p2.skills for i in sl.items]
    return ATS.analyze(jd, plan.get("keywords", []), base_tex, ATS.pdf_text(built.pdf), load_master(), skills, " ".join(bullets).replace("**", ""))


def rebuild(base_key: str, plan: dict, outdir: Path, reverted: set[str]) -> Built:
    parsed = T.parse((ROOT / BASES[base_key]["file"]).read_text())
    return compile_tex(render_tex(parsed, plan, reverted), outdir, "resume", skills_check_pairs(parsed, plan, reverted))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Tailor a base resume to a job description from the command line.")
    ap.add_argument("--base", default="auto", choices=["auto", "ds", "ml", "swe"])
    ap.add_argument("--jd-file", required=True)
    ap.add_argument("--out", default="out/cli")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    r = generate(a.base, Path(a.jd_file).read_text(), Path(a.out), get_provider(a.mock))
    b = r["built"]
    print(f"base={r['base']} provider={r['provider']} ok={b.ok} pages={b.pages} bottom={b.bottom:.0f}")
    for w in r["plan"]["warnings"] + r["log"]:
        print(" -", w)
    print("changed:", changed_slots(r["plan"]))
    print("pdf:", b.pdf)
