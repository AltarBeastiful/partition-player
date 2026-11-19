"""Run `partition-player recognize` on several pages at once, each in its own process.

Workers times threads stays within the cores: every worker gets its own cores // workers cores
(a CPU affinity mask, because onnxruntime ignores OMP_NUM_THREADS and sizes its pool from the cores
it may run on) and the OMP-style variables say the same for the other libraries. One worker (the default) is the old sequential run, environment untouched.
Results come back in the order of the page list, and a page that fails is reported, not raised.
"""
import os
import queue
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
               "ORT_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def thread_cap(jobs: int, cores: int) -> int:
    return max(1, cores // max(1, jobs))


def recognize_all(tasks, cli, jobs: int = 1, cores: int | None = None) -> list[dict]:
    """tasks: (name, image, out_dir). Returns {name, ok, seconds, error} per task, in task order."""
    cores = cores or os.cpu_count() or 1
    env = None
    if jobs > 1:
        env = dict(os.environ, **{v: str(thread_cap(jobs, cores)) for v in THREAD_VARS})

    slots: queue.Queue = queue.Queue()
    if jobs > 1:
        avail = sorted(os.sched_getaffinity(0))[:cores]
        per = thread_cap(jobs, len(avail))
        for k in range(jobs):
            slots.put(set(avail[k * per:(k + 1) * per]) or set(avail))

    def one(task):
        name, img, out = task
        t0 = time.time()
        mine = slots.get() if jobs > 1 else None
        try:
            r = subprocess.run([str(cli), "recognize", str(img), "-o", str(out)],
                               capture_output=True, text=True, env=env,
                               preexec_fn=(lambda: os.sched_setaffinity(0, mine)) if mine else None)
        finally:
            if mine:
                slots.put(mine)
        err = None if r.returncode == 0 else " ".join((r.stderr or "").strip().splitlines()[-1:]) or f"exit {r.returncode}"
        return {"name": name, "ok": r.returncode == 0, "seconds": round(time.time() - t0, 1), "error": err}

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(one, tasks))
