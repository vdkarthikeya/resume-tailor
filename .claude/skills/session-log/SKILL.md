---
name: session-log
description: Append to docs/RUNNING_NOTES.md when the user says wrap up, ends a chat, or after a major decision. Also read that file at the start of a session for prior context. Use whenever the user says wrap up, wrap-up, log this session, or update the running notes.
---

# Session log skill

**Trigger:** user says **wrap up** (or wrap-up / log this session / update running notes).  
**Log file (always):** [`docs/RUNNING_NOTES.md`](../../../docs/RUNNING_NOTES.md) — also listed in [`CLAUDE.md`](../../../CLAUDE.md).

## At session start

Read `docs/RUNNING_NOTES.md` (newest entry first) before other work.

## On "wrap up"

1. Open [`docs/RUNNING_NOTES.md`](../../../docs/RUNNING_NOTES.md).
2. **Prepend** a new entry at the top (below the intro blurb, above older entries). Newest first.
3. Use this shape:

```markdown
## YYYY-MM-DD (short title)

### Context
- What the user asked / why this session existed.

### Done
- Concrete work: files touched, PRs, commands, tests.

### Decisions
- Locked choices (even “we decided not to X”).

### Open
- What the next session should pick up.
```

4. Be factual and short. Link paths and PR URLs. Do not invent work that did not happen.
5. If the session only asked a question with no repo change, still log the decision or answer so context is not lost.
6. Commit and push `docs/RUNNING_NOTES.md` with any other unfinished changes from the session.
7. Confirm briefly that the log was updated (path + entry title).
