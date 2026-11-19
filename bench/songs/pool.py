"""Run `partition-player recognize` on several pages at once, each in its own process.

Workers times threads stays within the cores: every worker gets its own cores // workers cores
(a CPU affinity mask, because onnxruntime ignores OMP_NUM_THREADS and sizes its pool from the cores
it may run on) and the OMP-style variables say the same for the other libraries. One worker (the default) is the old sequential run, environment untouched.
Results come back in the order of the page list, and a page that fails is reported, not raised.
"""
import os
import queue
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
               "ORT_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def thread_cap(jobs: int, cores: int) -> int:
    return max(1, cores // max(1, jobs))


def available_cores(cores: int | None = None) -> list[int]:
    """The cores this process may use (at most `cores` of them): the one list the thread caps and the
    slots both come from. Without sched_getaffinity (not Linux) it is range(cpu_count)."""
    if hasattr(os, "sched_getaffinity"):
        mine = sorted(os.sched_getaffinity(0))
    else:
        mine = list(range(os.cpu_count() or 1))
    return mine[:cores] if cores else mine


# Run in a fresh interpreter: pin to the given cores, then replace itself with the real command.
# Done in the child, after the fork, so the parent (and the other worker threads) are untouched, and
# without preexec_fn, which is not safe to use from threads.
_PIN = "import os,sys; os.sched_setaffinity(0, {int(c) for c in sys.argv[1].split(',')}); os.execv(sys.argv[2], sys.argv[2:])"


def recognize_all(tasks, cli, jobs: int = 1, cores: int | None = None) -> list[dict]:
    """tasks: (name, image, out_dir). Returns {name, ok, seconds, error} per task, in task order."""
    avail = available_cores(cores)
    env = None
    if jobs > 1:
        env = dict(os.environ, **{v: str(thread_cap(jobs, len(avail))) for v in THREAD_VARS})

    slots: queue.Queue = queue.Queue()
    pin = jobs > 1 and hasattr(os, "sched_setaffinity")
    if pin:
        per = thread_cap(jobs, len(avail))
        for k in range(jobs):
            slots.put(avail[k * per:(k + 1) * per] or avail)

    def one(task):
        name, img, out = task
        t0 = time.time()
        mine = slots.get() if pin else None
        try:
            argv = [str(cli), "recognize", str(img), "-o", str(out)]
            if mine:
                argv = [sys.executable, "-c", _PIN, ",".join(map(str, mine)), *argv]
            r = subprocess.run(argv, capture_output=True, text=True, env=env)
        finally:
            if mine:
                slots.put(mine)
        err = None if r.returncode == 0 else " ".join((r.stderr or "").strip().splitlines()[-1:]) or f"exit {r.returncode}"
        return {"name": name, "ok": r.returncode == 0, "seconds": round(time.time() - t0, 1), "error": err}

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(one, tasks))
