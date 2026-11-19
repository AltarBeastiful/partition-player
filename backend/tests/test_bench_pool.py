"""The benchmark runner's parallel pages: order, a failed page, the thread cap.

The real check is bench/songs/check_jobs.py (parallel vs sequential on real pages); this one only
needs a fake CLI, so it runs in the normal suite.
"""
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bench" / "songs"))
from pool import recognize_all, thread_cap  # noqa: E402

FAKE = """#!/bin/sh
# recognize IMG -o OUT : sleeps longer for early pages so they finish last
img="$2"; out="$4"
case "$img" in *bad*) echo boom >&2; exit 3;; esac
case "$img" in *a.png) sleep 0.4;; esac
mkdir -p "$out"; echo "$OMP_NUM_THREADS" > "$out/threads"; grep Cpus_allowed_list /proc/self/status | cut -f2 > "$out/cpus"
"""


def fake_cli(tmp_path):
    p = tmp_path / "cli"
    p.write_text(FAKE.replace('img="$2"; out="$4"', 'img="$2"; out="$4"'))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def tasks(tmp_path, names):
    return [(n, tmp_path / f"{n}.png", tmp_path / "run" / n) for n in names]


def test_results_come_back_in_page_order_and_a_failure_does_not_stop_the_rest(tmp_path):
    res = recognize_all(tasks(tmp_path, ["a", "bad", "c"]), fake_cli(tmp_path), jobs=3, cores=12)
    assert [r["name"] for r in res] == ["a", "bad", "c"]
    assert [r["ok"] for r in res] == [True, False, True]
    assert "boom" in res[1]["error"]
    assert (tmp_path / "run" / "c" / "threads").exists()


def test_workers_times_threads_stay_within_the_cores(tmp_path):
    assert thread_cap(4, 16) == 4 and thread_cap(3, 16) == 5 and thread_cap(32, 16) == 1
    res = recognize_all(tasks(tmp_path, ["a", "c"]), fake_cli(tmp_path), jobs=4, cores=16)
    assert (tmp_path / "run" / "a" / "threads").read_text().strip() == "4"


def test_each_running_worker_is_pinned_to_its_own_cores(tmp_path):
    # onnxruntime ignores OMP_NUM_THREADS and sizes its pool from the cores it may run on
    res = recognize_all(tasks(tmp_path, ["a", "c"]), fake_cli(tmp_path), jobs=2, cores=4)
    assert all(r["ok"] for r in res)
    cpus = [(tmp_path / "run" / n / "cpus").read_text().strip() for n in ("a", "c")]
    assert cpus[0] != cpus[1]
    for c in cpus:
        assert len(c.split(",")) == 2 or "-" in c  # two cores each


def test_driver_caps_onnxruntime_threads_only_when_asked(monkeypatch):
    from partition_player.pipeline.engines import homr_driver as d
    seen = []

    class FakeOpts:
        intra_op_num_threads = 0
        inter_op_num_threads = 0

    class FakeOrt:
        SessionOptions = FakeOpts

        @staticmethod
        def InferenceSession(path, sess_options=None, **kw):
            seen.append(sess_options)

    monkeypatch.delenv("PP_ORT_THREADS", raising=False)
    d.cap_ort_threads(FakeOrt)
    FakeOrt.InferenceSession("m")
    assert seen[-1] is None  # production default untouched
    monkeypatch.setenv("PP_ORT_THREADS", "1")
    d.cap_ort_threads(FakeOrt)
    FakeOrt.InferenceSession("m")
    assert seen[-1].intra_op_num_threads == 1
