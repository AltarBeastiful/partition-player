"""Run the model pass on one case and one route, with the core directly (lyrics_pass.run), and count.

A case is a page: the score the pipeline produced (`engine`), the ground truth, and the spans to ask about.
The gate is `broken`: notes right before the pass that are wrong after it, after validation and apply.
"""
from __future__ import annotations

import copy
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from partition_player.model import lyrics_pass  # noqa: E402
from partition_player.model.route import Route  # noqa: E402

from client import Meter, MeteredClient  # noqa: E402
from metrics import compare, lyric_compare  # noqa: E402


@dataclass
class Case:
    name: str
    engine: ET.Element
    truth: ET.Element
    spans: list[dict]


@dataclass
class Result:
    route: str
    case: str
    fixed: int = 0
    broken: int = 0
    wrong_before: int = 0
    lyric_fixed: int = 0
    lyric_broken: int = 0
    rejections: int = 0      # operations or answers the validator dropped
    escalated: int = 0
    skipped: str = ""
    seconds: float = 0.0     # time spent in model calls
    cost: float | None = 0.0
    calls: int = 0
    reasons: list[str] = field(default_factory=list)
    after: ET.Element | None = None


def run_case(case: Case, route: Route, label: str, client_factory, prices=None) -> Result:
    """`client_factory(meter)` returns the client for this run (live, replay or script)."""
    res = Result(label, case.name)
    meter = Meter()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "score.musicxml"
        ET.ElementTree(case.engine).write(path, encoding="utf-8", xml_declaration=True)
        out = lyrics_pass.run(path, case.spans, route, client_factory(meter))
    after = copy.deepcopy(case.engine)
    lyrics_pass.apply_changes_by_staff(after, out["changes"])
    res.after = after
    res.rejections = len(out["dropped"])
    res.reasons = [str(x.get("reason", "")) for x in out["dropped"]]
    res.escalated = len(out["escalated"])
    res.calls = sum(m["calls"] for m in meter.by_model.values())
    res.seconds = meter.seconds()
    res.cost = meter.cost(prices)
    for span in case.spans:
        c = compare(case.truth, case.engine, after, span["from"], span["to"])
        if not c.comparable:
            res.skipped = "measure count differs from the ground truth"
            break
        res.fixed += c.fixed
        res.broken += c.broken
        res.wrong_before += c.wrong_before
        if span.get("lyrics_source"):
            f, b = lyric_compare(case.truth, case.engine, after, span["from"], span["to"])
            res.lyric_fixed += f
            res.lyric_broken += b
    return res


def summarise(results: list[Result]) -> dict:
    ok = [r for r in results if not r.skipped]
    cost = [r.cost for r in ok]
    return {
        "pages": len(ok), "skipped": len(results) - len(ok),
        "wrong_before": sum(r.wrong_before for r in ok),
        "fixed": sum(r.fixed for r in ok), "broken": sum(r.broken for r in ok),
        "lyric_fixed": sum(r.lyric_fixed for r in ok), "lyric_broken": sum(r.lyric_broken for r in ok),
        "rejections": sum(r.rejections for r in ok), "escalated": sum(r.escalated for r in ok),
        "calls": sum(r.calls for r in ok),
        "cost_per_page": None if not ok or any(c is None for c in cost) else sum(cost) / len(ok),
        "seconds_per_page": sum(r.seconds for r in ok) / len(ok) if ok else 0.0,
    }


def table(rows: dict[str, dict]) -> str:
    """Markdown table, one row per route. The gate column is PASS only when broken notes and syllables are 0."""
    head = ("| Route | Pages | Notes wrong before | Notes fixed | Notes broken | Syllables fixed / broken | Validator rejections | "
            "Escalated | Cost per page | Time per page | Gate |\n|---|---|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for name, s in rows.items():
        cost = "n/a" if s["cost_per_page"] is None else f"${s['cost_per_page']:.4f}"
        gate = "PASS" if s["broken"] == 0 and s["lyric_broken"] == 0 and s["pages"] else "FAIL"
        lines.append(f"| {name} | {s['pages']} (+{s['skipped']} skipped) | {s['wrong_before']} | {s['fixed']} | {s['broken']} | "
                     f"{s['lyric_fixed']} / {s['lyric_broken']} | {s['rejections']} | {s['escalated']} | {cost} | {s['seconds_per_page']:.1f} s | {gate} |")
    return "\n".join(lines)
