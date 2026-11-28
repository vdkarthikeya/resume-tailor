---
name: resume-qa
description: Run the mandatory 4-step resume QA gate (map company language, XYZ rewrite, score to 80%+, 10-second hiring-manager skim) before any resume wording change is committed or sent. Use when editing resumes/*.tex, bank bullets, reviewing a tailored PDF, or when the user asks to update or revamp resume content.
---

# Resume QA skill

## Instructions

1. Open and follow the full gate in [`RESUME_RULES.md`](../../../RESUME_RULES.md) (repo root). That file is the source of truth for prompts, pass conditions, and the handoff checklist.
2. Run Steps 1–4 in **one chat**, for **one job description** at a time.
3. Do not invent facts. Use `master_doc.md` as the only fact source; ask before assuming experience exists.
4. Pass only when score ≥ 80% (or a documented true-gap ceiling) **and** the hiring-manager skim would interview.
5. After the gate passes, continue with the **resume-content-sync** skill before commit/send.

## Quick reminder

- Target bases: **SWE** + one **ML/DS** track; do not add PM content.
- XYZ, under ~20 words, company language only when earned.
- Nothing goes on a resume the user cannot defend live.
