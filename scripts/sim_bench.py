import sys, time, tempfile, pathlib  # python scripts/sim_bench.py 6  (simulated seconds per model call)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import app as A, tailor as T
LAT=float(sys.argv[1])
class Slow(T.MockProvider):
    def tailor(self,*a,**k): time.sleep(LAT); return super().tailor(*a,**k)
    def pick_base(self,*a,**k): time.sleep(LAT/4); return super().pick_base(*a,**k)
JD="Machine learning engineer intern. We use PyTorch, embeddings and LightGBM to build models. "*4
def run(workers,n=6):
    A.OUT=pathlib.Path(tempfile.mkdtemp()); A.EXEC=ThreadPoolExecutor(max_workers=workers); A.QUEUE.clear(); A.FUTURES.clear(); A.PROVIDER_OVERRIDE=Slow()
    c=TestClient(A.app); t=time.time()
    c.post("/api/batch",json={"items":[{"jd":JD,"base":"auto"}]*n,"mock":True})
    while True:
        j=c.get("/api/jobs").json()["jobs"]
        if all(x["status"] in("done","failed","error") for x in j): break
        time.sleep(0.1)
    assert all(x["status"]=="done" for x in j),[x.get("error") for x in j]
    return time.time()-t
for w in (1,3):
    print(f"latency {LAT}s per model call, 6 jobs, {w} worker(s): {run(w):.1f}s")
