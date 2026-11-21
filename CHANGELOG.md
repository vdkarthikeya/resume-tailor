# Changelog

## 2026-11-20 (later still): retry, auto-track, duplicates, saved queue, email, sync check
See the README entry of the same name. 9 new tests, 77 in total.

## 2026-11-20 (Next Step numbers)
- Next Step bank bullets and the Master Doc entry now carry counted numbers from the repo: about 3,000 lines, 15 source notes, 3 languages, 34 browser checks, 27 commits.

## 2026-11-20 (later): Resume Tailor back in the bank
- Re-added `resume_tailor` to `bank/projects.json` (4 bullets), emptied `NEVER_LIST_PROJECTS`, replaced the ban test with two tests (in the bank, and pickable for a job), updated `master_doc.md` and the README. Base resumes unchanged. 68 tests pass.

## 2026-11-20: queue, speed, alerts, layout

### What changed
- **Batch queue.** `POST /api/batch` takes up to 25 jobs (pasted text or just a link). A pool of workers (`RESUME_WORKERS`, default 3) runs them side by side. `GET /api/jobs` lists them, `GET /api/jobs/{id}` returns the full review payload, `POST /api/jobs/{id}/cancel` cancels a waiting one, `POST /api/jobs/clear` clears finished rows. One failed job never stops the others. `/api/generate` still works as before.
- **Page.** "Tailor my resume" now queues and returns at once (the box clears for the next job). "Queue several links at once" takes one link per line. The queue card shows waiting, working (with a timer), done, failed, with Open, PDF and Cancel.
- **Auto-download.** The PDF downloads when a job finishes, named `Dhana_Karthikeya_Ventrapragada_Resume_<Company>.pdf`.
- **Notification bell.** Badge count, a list of finished jobs (click to open), optional desktop alert and sound, and the tab title shows progress. Each option can be switched off in the bell panel (saved in the browser).
- **Tracker.** Finished rows show a Tracked or Not tracked tag and an Add to tracker button. Logging from the tracker bar updates the tag too.
- **Layout.** Input and queue on the left, the PDF with the Add to tracker bar (sticky) in the middle, results and review edits on the right. Two columns on mid-size screens, one on phones. The latest finished resume opens after a reload.
- **Model calls (`tailor.py`).**
  - The prompt now starts with the parts that never change (project bank, courses, Master Doc, then the base resume) and ends with the job text, with cache breakpoints, so the API can reuse the long prefix across retries and batches.
  - Unchanged bullets come back as just `from_index`; approved project bullets as just `bank_id`; the locked CS 61A entry is not sent.
  - Auto-pick skips the model when one role clearly wins on keywords (`FAST_PICK_MIN_HITS`, `FAST_PICK_RATIO`, off with `RESUME_FAST_PICK=0`), otherwise uses a small model (`RESUME_PICK_MODEL`, `RESUME_CLAUDE_PICK_MODEL`).
  - At most 2 attempts instead of 3 (`RESUME_MAX_ATTEMPTS`). The same checks still decide whether to retry.
  - One provider (one API client) is reused by every request.
  - Every run records timings (pick base, each model call, each build, total), shown by the CLI and returned as `timings`.
  - CLI accepts `--base pm`.
- **Tests.** 12 new tests: short answers, bank ids, locked entry, prompt prefix stability, fast pick, attempt cap and timings, queue validation, parallel run, failure isolation, cancel, a real end-to-end batch, and the tracked flag.
- **Tools.** `scripts/bench_queue.py` measures a batch on a running server.

### Performance: what is measured and what is not
Measured here (no API key, so no real model calls):
- Queue machinery on the real pipeline in dry-run mode (8 jobs, about 0.3 s each, LaTeX only): 2.52 s with 1 worker, 1.33 s with 3 workers, which is 1.9x faster and 47% less wall time. Dry-run jobs are too short to show the full effect.
- Prompt: about 91,000 characters (roughly 22,700 tokens) per tailoring call. 92% of it is the shared prefix and 97% with the base resume, so up to that share can be served from the API cache. Before this change the job text came first, so none of it could be cached.
- Model calls per job (not seconds): the auto-pick used to be a full-size call and a job could make up to 3 tailoring calls, so up to 4 big calls and typically 3. Now the pick is free or a small call, and a job makes at most 2 tailoring calls: typically 2 big calls (a third fewer), worst case 2 (half as many).

Estimated, not measured:
- Wall time for a batch is about `ceil(jobs / workers) x time per job`, against `jobs x time per job` before. With 3 workers that is 67% less for 3 or 6 jobs, 60% less for 5 or 10 jobs.
- API cost of the input side: a cache read costs about a tenth of a normal input token and the first write about 1.25 times (standard multipliers). For a batch of 6 jobs (about 12 calls) that is roughly 78% fewer input tokens billed. A single job with one retry is about 32% fewer.
- Shorter answers saved less than expected: the entry bullets are only about 1,200 characters, so returning unchanged ones as an index saves roughly 20 to 45% of that part, a few seconds at most.

Not known yet: the real seconds saved per job from caching, and whether caching helps in Claude Code subscription mode, where the CLI manages its own cache. Run `python scripts/bench_queue.py jd1.txt jd2.txt jd3.txt` (without `--mock`) for real numbers, and compare with the old code by checking out `fc03e80` and timing `python tailor.py --jd-file jd1.txt`.
