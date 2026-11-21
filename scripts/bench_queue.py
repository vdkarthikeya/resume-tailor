"""Measure the queue on a running server: python scripts/bench_queue.py jd1.txt jd2.txt ... [--url http://127.0.0.1:8000] [--mock]

Submits every job description at once, waits for all of them and prints, per job, how long it took and where the
time went (picking the base, each model call, each LaTeX build), then the wall time for the whole batch against what
running them one after another would have taken (the sum of the per-job times). Run it against the real model, not
--mock, to get numbers that mean anything: mock jobs only measure LaTeX."""
import argparse
import sys
import time
from pathlib import Path

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="job description text files")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--mock", action="store_true", help="dry run without the model (only measures LaTeX and the queue)")
    ap.add_argument("--repeat", type=int, default=1, help="submit each file this many times")
    ap.add_argument("--base", default="auto")
    a = ap.parse_args()
    items = [{"jd": Path(f).read_text(), "base": a.base} for f in a.files for _ in range(a.repeat)]
    c = httpx.Client(base_url=a.url, timeout=60)
    t0 = time.time()
    r = c.post("/api/batch", json={"items": items, "mock": a.mock})
    r.raise_for_status()
    ids = {j["id"] for j in r.json()["jobs"]}
    workers = r.json()["workers"]
    while True:
        jobs = [j for j in c.get("/api/jobs").json()["jobs"] if j["id"] in ids]
        if all(j["status"] in ("done", "failed", "error", "cancelled") for j in jobs):
            break
        time.sleep(0.5)
    wall = time.time() - t0
    print(f"{'job':<34}{'status':<8}{'took':>7}  {'pick':>6}  model calls (s)            builds (s)")
    total = 0.0
    for j in jobs:
        took = (j["finished"] or 0) - (j["started"] or 0)
        total += took
        t = j.get("timings") or {}
        print(f"{j['label'][:33]:<34}{j['status']:<8}{took:7.1f}  {t.get('pick_base', 0):6.1f}  {str(t.get('llm', [])):<26} {t.get('compile', [])}")
    ok = sum(j["status"] == "done" for j in jobs)
    print(f"\n{ok}/{len(jobs)} done with {workers} workers")
    print(f"wall time for the batch : {wall:6.1f}s")
    print(f"one after another       : {total:6.1f}s (sum of the per-job times)")
    if wall > 0:
        print(f"saved by parallelism    : {total - wall:6.1f}s  ({100 * (total - wall) / total:.0f}% less, {total / wall:.2f}x faster)")
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
