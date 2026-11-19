"""Check that a parallel benchmark run gives the same results as a sequential one.

Usage: .venv-oemer/bin/python bench/songs/check_jobs.py [--set S] [--only NAME] [--jobs N]
Runs run_bench.py twice over the same pages (once with --jobs 1, once with --jobs N, default 4) and
compares the two results.json in every field but "seconds". Exit code 0 when they are identical.
--only is a substring of the page name; without it, every page of the set runs twice.
"""
import json, subprocess, sys, shutil, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_pages import flag_value, out_dir, which_set  # noqa: E402


def strip(rows):
    return [{k: v for k, v in r.items() if k != "seconds"} for r in rows]


def main() -> int:
    out = out_dir(which_set(sys.argv))
    passthru = [a for f in ("--set", "--only") if f in sys.argv for a in (f, flag_value(sys.argv, f, ""))]
    runs = {}
    for jobs in ("1", flag_value(sys.argv, "--jobs", "4")):
        t0 = time.time()
        subprocess.run([sys.executable, str(HERE / "run_bench.py"), *passthru, "--jobs", jobs], check=True)
        print(f"\n--jobs {jobs}: {time.time() - t0:.0f} s wall")
        runs[jobs] = json.loads((out / "results.json").read_text())
        shutil.copy(out / "results.json", out / f"results.jobs{jobs}.json")
    a, b = (strip(r) for r in runs.values())
    same = a == b
    print(f"\n{len(a)} pages sequential, {len(b)} parallel: {'IDENTICAL' if same else 'DIFFERENT'} (all fields but seconds)")
    if not same:
        for x, y in zip(a, b):
            if x != y:
                print("  differs:", x["name"])
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
