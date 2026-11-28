---
name: session-log
description: Append to docs/RUNNING_NOTES.md so the next Cursor or Claude Code session has context about what this chat did. Use at the end of every session, after major decisions, or when the user asks to update the running log.
---

# Session log skill

## Instructions

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
6. Commit the updated `docs/RUNNING_NOTES.md` with the rest of the session’s changes when there are any.
