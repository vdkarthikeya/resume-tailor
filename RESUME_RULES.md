# Resume QA rules (mandatory gate)

Every resume wording change in this repo must pass this gate before it is committed, applied, or sent. That includes edits to `resumes/*.tex`, `bank/projects.json`, `bank/courses.json`, and review of any tailored PDF before you track or submit it.

Do **not** commit or send until all four steps pass. Run them in **one chat**, in order, for **one job** at a time. A new role means a new run.

Adapted from [Sabrina Ramonov’s 4-prompt chain](https://substack.com/@sabrinaramonov/note/c-241937172). Honesty, Master Doc evidence, and layout rules below are this project’s.

Session entrypoint for Cursor / Claude Code: [`CLAUDE.md`](CLAUDE.md) (always loaded). On-demand skill: [`.claude/skills/resume-qa/SKILL.md`](.claude/skills/resume-qa/SKILL.md).

## Target bases (decision)

Keep **two** public / maintained tracks — not four:

| Base | Use for | Status |
|---|---|---|
| **SWE** (`resumes/swe.tex`) | Software engineer, backend, full-stack, infra | Keep |
| **ML/DS** (merge of today’s `ml.tex` + `ds.tex`) | ML engineer, applied ML, data scientist, analytics | Keep as one track |
| **PM** (`resumes/pm.tex`) | Product / program | **Retire** — not a target path |

**Do not keep separate hosted ML and DS resumes.** One strong technical ML/DS base is enough: lead ML-first (models, PyTorch, SightLine, IDX) and let Resume Tailor reorder bullets / swap bank projects toward stats or analytics when the JD is a pure DS role. Splitting ML vs DS only adds maintenance and dilutes the brand when the goal is to look technically deep, not product-shaped.

Until the merge lands in code, still keep `ml.tex` and `ds.tex` in sync with each other on shared facts; do not invest in new PM content.

## Content sync (always with wording changes)

When you (or an agent) update resume content, update **all** of these in the same change set — not “later”:

1. **`master_doc.md`** — every new real fact, metric, tool, or wording decision goes here first (and into the Claude Doc “Master Doc: Everything I've Done”). No resume line may cite a number that is missing from the Master Doc.
2. **Bases / bank** — `resumes/*.tex`, `bank/projects.json`, `bank/courses.json` as needed.
3. **Website** — [vdkarthikeya.github.io](https://github.com/vdkarthikeya/vdkarthikeya.github.io): copy matching `resumes/src/resume_*.tex`, rebuild hosted PDFs under `resumes/`, and update site project copy in `data.js` when titles/bullets change. Verify with `python scripts/sync_check.py --site <clone of vdkarthikeya.github.io>`.

Skip the website only for pure tool-code changes with zero resume wording change.

## When it applies

| Change | Gate required? | Also sync Master Doc + site? |
|---|---|---|
| Base resume bullets / skills / coursework (`resumes/*.tex`) | Yes | Yes |
| Project bank bullets (`bank/projects.json`) | Yes | Yes |
| Course bank (`bank/courses.json`) when names affect resume wording | Yes | Yes (Master Doc; site if hosted copy shows it) |
| Post-tailor review before apply / tracker / send | Yes | Master Doc if new facts; site only if a base/PDF changed |
| Master Doc fact sync with no resume wording change | No (still keep facts honest) | Master Doc only |
| Code-only tool changes (`tailor.py`, `ats.py`, …) | No | No |

## Non-negotiables

These override any model suggestion from the prompts below.

1. **Never invent** a skill, tool, title, date, outcome, or number.
2. **Numbers only** if they already appear in `master_doc.md`, a base resume, or an approved bank bullet. Do not compute new ones.
3. **Ask before assuming** experience exists. If it is not in the Master Doc, it is a gap — list it, do not stuff it into Skills or bullets.
4. **XYZ bullets:** Accomplished [X] as measured by [Y] by doing [Z], written as plain English. Prefer under **20 words**. If there is no real Y, use a concrete checkable outcome (never invent a metric).
5. **Voice:** plain, direct, strong action verb. No bold, no `**`, no em dashes, no en dashes, no `--`, no filler (`leveraged`, `spearheaded`, `passionate`, `responsible for`, `helped with`).
6. **Company language only when earned.** Use the job’s exact term when the Master Doc supports it. Never use a job term you did not earn.
7. **Gaps stay gaps.** Unsupported requirements go in an honest mismatch list. Never keyword-stuff.
8. **Evidence for rewrites.** Any new or rewritten bullet must be supportable by verbatim Master Doc quotes (same bar as Resume Tailor).
9. **Layout.** One full page. Single column. Plain hyphen dates. Section order Education → Experience → Projects → Technical Skills. Degree line stays `B.A. in Data Science and Applied Mathematics`. Slot-only edits in LaTeX (never regenerate the `.tex` shell).
10. **Nothing you cannot defend** in a live conversation goes on the resume.

## Inputs (every run)

Paste all of these into the same chat before Step 1:

- Target role and company (if known)
- Full job description (plain text)
- Current resume as **plain text** (copy from PDF / compiled text, not LaTeX source)
- Fact source: relevant excerpts from `master_doc.md`, or state “use Master Doc as the only fact source; ask me before adding anything not in it”

---

## Step 1 — Map company language

**Pass condition:** Every high-priority skill / outcome / trait is mapped to a closest bullet or marked as a true gap. No rewrites yet.

### Prompt

```
You are reviewing my resume against one job description. Diagnosis only — do not rewrite yet.

Fact source: Master Doc / notes I provide. Never invent experience. If something is missing from my facts, call it a gap and ask before assuming I have it.

1. Extract the company's exact language for skills, outcomes, and traits. Rank by importance for THIS role.
2. Map each item to my closest resume bullet (quote the bullet). If nothing maps, mark it GAP.
3. Split gaps into:
   - Fixable now: I likely did this, but it is not written (ask me one clarifying question per item before treating it as real)
   - True gap: Master Doc does not support it — leave it off the resume
4. List the three resume lines doing the least work for this role, quoted exactly, with one sentence each on why.

Job description:
[PASTE]

Resume (plain text):
[PASTE]

Master Doc / facts:
[PASTE OR "ask me before assuming"]
```

---

## Step 2 — Clarify and rewrite (XYZ + company language)

**Pass condition:** Before/after for every changed bullet; each rewrite ≤20 words when possible; metric-driven or concrete outcome; no fabrication; company terms used only where earned.

Ask at most **3 clarifying questions** total before rewriting. Prefer questions that unlock real numbers already lived but not yet in the Master Doc — then add those numbers to `master_doc.md` before they go on a resume.

### Prompt

```
Same chat. Use the map and gaps from Step 1.

Ask up to 3 clarifying questions if needed to unlock real metrics or confirm whether a "fixable" gap is true. Then stop asking and rewrite.

Rewrite rules:
- Company exact language only where my Master Doc supports it
- Never fabricate skills, tools, titles, dates, or numbers
- XYZ: Accomplished [X] as measured by [Y] by doing [Z], as natural English
- Each bullet under 20 words when possible, metric-driven, high impact
- Plain text only: no bold, no em/en dashes, no filler verbs
- If a number is missing, ask or use a concrete scope outcome and mark [no metric yet] — never invent

Output:
1. Before vs after for every bullet you change (and which entry it belongs to)
2. One sentence per rewrite on why it is stronger for THIS role
3. List of numbers / facts still needed from me
4. Updated honest gaps list (still unsupported — do not add these)

If I answer clarifying questions with new real facts, treat them as candidates for Master Doc — do not put them on the resume until I confirm they are recorded.
```

---

## Step 3 — Score to 80%+

**Pass condition:** Overall score ≥ **80%**, or a written plan that reaches 80% using only Master Doc–supported changes (no stuffing true gaps). Weak bullets flagged with fixes.

### Scoring rubric (equal weight unless you note otherwise)

| Dimension | What “high” means |
|---|---|
| Keyword match | Job’s hard-skill terms appear verbatim where earned (Skills + at least one bullet) |
| Skills | Skills line leads with the job’s languages/tools; nothing unsupported |
| Outcomes | Bullets show measurable or concrete results, not duties |
| Role fit | Strongest matching experiences/projects are first; weak/off-target content cut or demoted |

Label each missing high-priority term:

- **Fixable with Master Doc wording** — reword / reorder / pick a better project
- **True gap** — leave off; do not chase the score by lying

### Prompt

```
Same chat. Score the CURRENT resume text (after Step 2 rewrites) against the job description.

Score out of 100 using four sub-scores that add up (or show equal 25-point weights):
1. Keyword match
2. Skills
3. Outcomes
4. Role fit

Then:
- Give the overall percentage
- List missing high-priority terms; mark each Fixable (Master Doc supports it) or True gap
- Flag weak bullets (quote them) and say exactly how to fix each without inventing facts
- Tell me exactly how to reach 80%+ using only honest, Master Doc–supported changes
- If already ≥80%, say what would push it higher without keyword stuffing

Do not rewrite the full resume again unless a specific weak bullet still fails XYZ.
```

If below 80%: return to Step 2 with the score feedback, then re-score. Do not proceed to Step 4 until ≥80% or you consciously accept a true-gap ceiling and document why.

---

## Step 4 — 10-second hiring-manager skim

**Pass condition:** Interview = **yes** (or yes-with-one-fix already applied). Biggest doubt has a concrete, honest fix. If interview = no, return to Step 2.

### Prompt

```
Same chat. Act as the hiring manager for this exact role. You skim resumes for about 10 seconds.

1. Would you interview me? Yes or no, and why (in your words, not mine).
2. What is your biggest doubt after 10 seconds?
3. How do I fix that doubt using only experience supported by my Master Doc? Give the exact bullet or skills change.
4. What do you remember after the skim? Does it match this role?

Be blunt. Do not soften a no.
```

---

## Repo handoff checklist (after all four steps pass)

Complete in order before `git commit` / send:

1. **Master Doc:** Add any newly confirmed real metrics or facts from clarifying answers to `master_doc.md` (and the Claude Doc source). **Required on every content update** — not optional / later.
2. **Bases / bank:** Apply accepted before/after wording to the active bases (`swe` + ML/DS track) and/or `bank/projects.json` (approved bullets only; keep one page; ≤3 projects). Do not add new PM-only content.
3. **Skills / coursework:** Only Master Doc–supported items; coursework from `bank/courses.json` only; no “In progress” labels.
4. **Website:** Sync `vdkarthikeya.github.io` (`resumes/src/`, hosted PDFs, `data.js` if project copy changed). Run `python scripts/sync_check.py --site <site clone>`.
5. **Tests:** `pytest tests` (needs LaTeX). Fix failures before commit.
6. **Tailor for this JD:** Run Resume Tailor so the automated gate (evidence quotes, banned claims, page fit, ATS parse) still passes.
7. **Final skim:** Re-read the compiled PDF plain text once. If Step 4’s doubt is still visible, do not send.

```text
[ ] Steps 1–4 passed in one chat for this JD
[ ] Score ≥ 80% (or true-gap ceiling documented)
[ ] Hiring manager = interview yes (doubt fixed)
[ ] master_doc.md (+ Claude Doc) updated for any new real facts
[ ] resumes/*.tex and/or bank/ updated
[ ] vdkarthikeya.github.io src + PDFs (+ data.js if needed) synced
[ ] sync_check.py --site green
[ ] pytest green
[ ] Tailored PDF reviewed; ready to send
```

## How this relates to Resume Tailor

| Layer | Role |
|---|---|
| `RESUME_RULES.md` (this file) | Human/agent QA before wording is trusted |
| `master_doc.md` | Only allowed facts; must stay in lockstep with resume edits |
| `vdkarthikeya.github.io` | Public hosted bases/PDFs; must match repo after wording changes |
| `tailor.py` SYSTEM + validators | Automated evidence, bans, XYZ, one-page fit |
| `ats.py` | Keyword coverage + PDF parse check after compile |

Automated tailoring does **not** replace Steps 1–4. Use this gate when changing bases/bank, and again when reviewing a tailored PDF for a real application.
