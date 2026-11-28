# Resume Tailor — session brief

This file loads at the start of every **Cursor** and **Claude Code** session. Keep it short. Deep procedures live in skills and linked docs — **read them when the task matches**; do not rely on this index alone.

## What this repo is

Local tool: paste a job → tailor a one-page LaTeX resume using only facts from `master_doc.md` and `bank/`. Layout is never regenerated; only slot text changes.

| Path | Role |
|---|---|
| `master_doc.md` | Only allowed facts / numbers |
| `resumes/*.tex` | Base resumes (target: **SWE** + one **ML/DS**; retire PM) |
| `bank/` | Approved projects and courses |
| `tailor.py` | Model prompt, bans, fit loop |
| `RESUME_RULES.md` | Mandatory 4-step QA gate before wording ships |
| `vdkarthikeya.github.io` | Hosted resumes/PDFs — must stay in sync |

## Hard rules (always)

- Never invent skills, tools, titles, dates, or numbers.
- Numbers only if already in Master Doc / bases / bank.
- XYZ bullets; plain text; no bold; no em/en dashes; no filler.
- Job keywords only when earned; true gaps stay gaps.
- One page; evidence quotes for rewrites; `pytest` before commit.
- Every resume **wording** change updates `master_doc.md` **and** the website in the same change set.

## Skills (read when relevant)

Skills live under [`.claude/skills/`](.claude/skills/). Cursor and Claude Code discover them automatically; invoke with `/skill-name` or when the task matches the skill description.

| Skill | When to use |
|---|---|
| [resume-qa](.claude/skills/resume-qa/SKILL.md) | Any resume wording change, base/bank edit, or pre-send review — run the 4-step gate |
| [resume-content-sync](.claude/skills/resume-content-sync/SKILL.md) | After accepted wording: sync Master Doc, bases/bank, and `vdkarthikeya.github.io` |

Canonical checklist (also linked from the resume-qa skill): [`RESUME_RULES.md`](RESUME_RULES.md).

## Common commands

```bash
./run.sh                          # UI at http://127.0.0.1:8000
pytest tests                      # needs LaTeX
python scripts/sync_check.py      # repo consistency
python scripts/sync_check.py --site ../vdkarthikeya.github.io
```

## How loading works

- **This file (`CLAUDE.md`)** — always applied in Cursor and Claude Code. No special setting required.
- **Skills** — catalog/descriptions load at start; full `SKILL.md` loads when relevant or when you `/`-invoke. Prefer skills for long procedures so every session does not burn the full checklist.
- **Do not** `@import` large docs into this file (Claude Code would inline them every session). Link + instruct “read and follow” instead.
