"""The model pass benchmark (ADR 0010, plan 0016 slice 3).

Usage (backend venv; see bench/model/README.md):
  python bench/model/run_bench.py --offline                         the harness on a synthetic page and a scripted route; no keys
  python bench/model/run_bench.py --routes haiku,sonnet,deepseek --live [--max-pages 3] [--lyrics] [--write] [--audio]
  python bench/model/run_bench.py --routes haiku --replay rec.json  answers from a recording made with --record

Keys come from PP_ANTHROPIC_API_KEY and PP_DEEPSEEK_API_KEY (never printed). A route without a key is skipped.
Results are written to bench/RESULTS.md only with --write and never for --offline.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))

import audio  # noqa: E402
import cases as cases_mod  # noqa: E402
import offline  # noqa: E402
from client import MeteredClient, load_recording  # noqa: E402
from harness import Case, run_case, summarise, table  # noqa: E402
from partition_player.model.route import Route  # noqa: E402

ENV = {"haiku": "PP_ANTHROPIC_API_KEY", "sonnet": "PP_ANTHROPIC_API_KEY", "deepseek": "PP_DEEPSEEK_API_KEY"}


def make_route(name: str, key: str, escalate: bool) -> Route:
    if name == "deepseek":
        r = Route.deepseek(key)
    elif name == "sonnet":
        r = Route.anthropic(key, model=Route.anthropic("").larger_model, larger_model="")
    else:
        r = Route.anthropic(key)
    return r if escalate else Route(r.base_url, r.api_key, r.model, r.vision, "")


def anton_case() -> Case | None:
    engine, truth = cases_mod.OUT / "homr" / "anton.musicxml", ROOT / "bench" / "samples" / "anton_yvan_boris_ground_truth.musicxml"
    if not engine.exists():
        return None
    e = ET.parse(engine).getroot()
    return Case("anton", e, ET.parse(truth).getroot(), [{"staff": 0, "from": 0, "to": len(e.find("part").findall("measure")) - 1}])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--live", action="store_true", help="really call the models (costs money)")
    ap.add_argument("--replay", type=Path, help="recorded answers (JSON)")
    ap.add_argument("--record", type=Path, help="with --live, store every answer in this file")
    ap.add_argument("--routes", default="haiku,sonnet,deepseek")
    ap.add_argument("--sets", default="leadsheets,voice_piano")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--lyrics", action="store_true", help="also ask the words spans (ground-truth verses as the typed source)")
    ap.add_argument("--anton", action="store_true", help="add the Anton photo (bench/out/homr/anton.musicxml)")
    ap.add_argument("--no-escalation", action="store_true", help="measure each model alone, without the larger-model retry")
    ap.add_argument("--price", action="append", default=[], help="MODEL_SUBSTRING=IN,OUT dollars per million tokens (deepseek has no built-in price)")
    ap.add_argument("--audio", action="store_true", help="render post-pass scores to bench/out/model/<route>/<page>.ogg")
    ap.add_argument("--write", action="store_true", help="append the table to bench/RESULTS.md")
    a = ap.parse_args()
    prices = {k: tuple(float(x) for x in v.split(",")) for k, v in (p.split("=") for p in a.price)}

    if a.offline:
        todo = [("offline (scripted route)", Route.anthropic("offline", larger_model=""), offline.case(), lambda m: MeteredClient(m, script=offline.script))]
        todo = [(label, route, [case], f) for label, route, case, f in todo]
    else:
        cs = cases_mod.load(a.sets.split(","), a.lyrics, a.max_pages)
        if a.anton and (c := anton_case()):
            cs.append(c)
        if not cs:
            print("no cases: run bench/songs/run_bench.py first (outputs under bench/out/songs/)", file=sys.stderr)
            return 2
        todo = []
        for name in a.routes.split(","):
            key = os.environ.get(ENV[name], "")
            if a.replay:
                rec = load_recording(a.replay)
                todo.append((name + " (replay)", make_route(name, "replay", not a.no_escalation), cs, lambda m, rec=rec: MeteredClient(m, recorded=rec)))
            elif a.live and key:
                import httpx
                todo.append((name, make_route(name, key, not a.no_escalation), cs,
                             lambda m, rec=load_recording(a.record) if a.record else None: MeteredClient(m, live=httpx.Client(), record_to=a.record, recorded=rec)))
            else:
                print(f"skip {name}: " + ("no --live" if key else f"{ENV[name]} is not set"))
    rows, all_results = {}, []
    for label, route, case_list, factory in todo:
        results = []
        for case in case_list:
            r = run_case(case, route, label, factory, prices)
            results.append(r)
            print(f"{label:28} {case.name:48} fixed {r.fixed:3} broken {r.broken:3} rejected {r.rejections:3} calls {r.calls}")
            if a.audio and r.after is not None:
                d = cases_mod.OUT / "model" / label.split()[0]
                d.mkdir(parents=True, exist_ok=True)
                x = d / (case.name.replace("/", "_") + ".musicxml")
                ET.ElementTree(r.after).write(x, encoding="utf-8", xml_declaration=True)
                for tag, root in (("pass", None), ("engine", case.engine), ("truth", case.truth)):
                    src = x
                    if root is not None:
                        src = d / f"{case.name.replace('/', '_')}.{tag}.musicxml"
                        ET.ElementTree(root).write(src, encoding="utf-8", xml_declaration=True)
                    why = audio.render(src, src.with_suffix(".ogg"))
                    if why:
                        print("  no audio:", why)
                        break
        rows[label] = summarise(results)
        all_results += results
    if not rows:
        print("nothing was run")
        return 0
    t = table(rows)
    print("\n" + t)
    if any(s["broken"] for s in rows.values()):
        print("\nGATE FAILED for: " + ", ".join(k for k, s in rows.items() if s["broken"]))
    if a.write and not a.offline:
        section = (f"\n## Model pass benchmark, {datetime.date.today()}\n\n"
                   f"Pages: {len(all_results) // max(len(rows), 1)} per route from sets {a.sets}"
                   f"{' with words spans' if a.lyrics else ''}{', escalation off' if a.no_escalation else ''}. "
                   "Counts are notes by slot against the ground truth, after validation and apply "
                   "(`bench/model/metrics.py`). Cost uses Haiku $1/$5 and Sonnet $3/$15 per million tokens; n/a means no price known. "
                   "Listening check: not yet done.\n\n" + t + "\n")
        with (ROOT / "bench" / "RESULTS.md").open("a") as f:
            f.write(section)
        print("written to bench/RESULTS.md")
    return 1 if any(s["broken"] for s in rows.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
