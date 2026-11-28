# Running Notes — Resume Tailor

Running log of what we do in each **Cursor / Claude Code** session on this repo (same idea as the website and Fung Fellowship agent projects). **Newest entry at the top.**

Required by [`CLAUDE.md`](../CLAUDE.md): read at session start; when the user says **wrap up**, append via [session-log](../.claude/skills/session-log/SKILL.md).

---

## 2026-11-27 (Resume QA gate, CLAUDE.md, session log)

### Context
- User watched a Facebook reel (Sabrina Ramonov 4-prompt chain); getting rejected a lot; wants a hard QA gate for every resume tweak.
- Also: sync Master Doc + website on content changes; boil down to SWE + ML/DS (drop PM); always-on `CLAUDE.md` for Cursor and Claude Code; keep a per-session running log like the other agent projects.

### Done
- [`RESUME_RULES.md`](../RESUME_RULES.md) — 4-step gate + honesty rules + Master Doc/website handoff.
- [`CLAUDE.md`](../CLAUDE.md) + skills: `resume-qa`, `resume-content-sync`, `session-log`.
- This file (`docs/RUNNING_NOTES.md`) as the session log.
- README workflow updated. PR https://github.com/vdkarthikeya/resume-tailor/pull/7 (CI green).

### Decisions
- Drop PM; target **SWE + one ML/DS** track (no separate hosted ML vs DS long-term).
- Session brief = `CLAUDE.md`; long procedures = skills; do not `@import` huge docs every session.
- Every agent session must append here.

### Open
- Merge `ml.tex` / `ds.tex` and remove `pm` from tailor UI, pick logic, tests, website.
- First real QA-gate pass to revamp the bases.
