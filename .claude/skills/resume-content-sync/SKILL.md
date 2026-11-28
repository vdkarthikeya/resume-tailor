---
name: resume-content-sync
description: Sync master_doc.md, resume bases/bank, and the vdkarthikeya.github.io website after any resume wording change. Use whenever resume content is updated, after resume-qa passes, or when the user asks to update the Master Doc or hosted resumes.
---

# Resume content sync skill

## Instructions

When resume wording changes (bases, bank, or accepted tailored edits that become the new default), update **all** of these in the same change set:

### 1. Master Doc

- Add every new real fact, metric, tool, or wording decision to [`master_doc.md`](../../../master_doc.md).
- Remind the user to sync the Claude Doc “Master Doc: Everything I've Done” if they keep that as the upstream source.
- No resume line may cite a number missing from the Master Doc.

### 2. Bases and bank

- Apply accepted wording to active bases under `resumes/` (SWE + ML/DS track; no new PM content).
- Update `bank/projects.json` / `bank/courses.json` when projects or courses change.
- Keep one page, ≤3 projects, plain bullets (no bold, no em dashes).

### 3. Website

Repo: [vdkarthikeya/vdkarthikeya.github.io](https://github.com/vdkarthikeya/vdkarthikeya.github.io)

- Copy matching sources to `resumes/src/resume_*.tex`.
- Rebuild hosted PDFs under `resumes/`.
- Update `data.js` if project titles or public copy changed.

### 4. Verify

```bash
python scripts/sync_check.py
python scripts/sync_check.py --site <clone of vdkarthikeya.github.io>
pytest tests
```

Skip the website only for pure tool-code changes with zero resume wording change.

## See also

- Full gate + checklist: [`RESUME_RULES.md`](../../../RESUME_RULES.md)
- Session index: [`CLAUDE.md`](../../../CLAUDE.md)
