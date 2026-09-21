"""Where every measure is on the review image (ADR 0005, decision 2).

The driver's `geometry.json` has, per system, the staff extent and the detected barlines in homr's
working coordinates, the transformer's measure count, and the chain back to upload pixels. This
module turns it into `layout.json` in review-image pixels: per system its box, its staves and its
measures' x ranges. Barlines give the measure boundaries when their count agrees with the measure
count (92 % of systems on the lead-sheet benchmark); otherwise the system is split evenly, which
still frames the right region of the print.
"""
from __future__ import annotations

EDGE_UNITS = 1.5   # a barline this close to the staff's end is its edge, not an inner boundary


def to_upload(chain: dict, x: float, y: float) -> tuple[float, float]:
    rx, ry = chain["resize"]
    cx, cy = chain["crop"]
    s = chain["scale"] or 1.0
    return (x / rx + cx) / s, (y / ry + cy) / s


def measure_bounds(system: dict) -> list[float]:
    """x boundaries of the system's measures in working coordinates, `measures + 1` values."""
    n = int(system.get("measures") or 0)
    x0, x1, unit = float(system["min_x"]), float(system["max_x"]), float(system.get("unit") or 1.0)
    if n <= 0:
        return [x0, x1]
    inner = [float(b) for b in system.get("bars", []) if x0 + EDGE_UNITS * unit < b < x1 - EDGE_UNITS * unit]
    if len(inner) == n - 1:
        return [x0, *inner, x1]
    return [x0 + (x1 - x0) * k / n for k in range(n + 1)]


def system_spans(geometry: dict, measure_count: int) -> list[tuple[int, int, int, list[float]]]:
    """Per system: (index, first measure of the final score, how many, x boundaries in working
    coordinates). The single place that decides which measure a point of the print belongs to, so
    the review strip (ADR 0005) and the evidence (plan 0008) can never disagree about it."""
    systems_in = geometry.get("systems", [])
    counts = [int(sy.get("measures") or 0) for sy in systems_in]
    total = sum(counts)
    exact = total == measure_count and measure_count > 0
    out: list[tuple[int, int, int, list[float]]] = []
    first = 0
    for i, sy in enumerate(systems_in):
        if exact:
            n = counts[i]
        else:
            done = sum(counts[:i + 1])
            n = round(measure_count * done / total) - first if total else 0
        bounds = measure_bounds(sy) if n == counts[i] else [sy["min_x"] + (sy["max_x"] - sy["min_x"]) * k / max(n, 1) for k in range(n + 1)]
        out.append((i, first, n, bounds))
        first += n
    return out


def estimated_bounds(system: dict) -> bool:
    """True when the system's detected barlines did not match its measure count, so `measure_bounds`
    split it evenly: which measure a notehead falls in is then a guess (plan 0008, a demotion)."""
    n = int(system.get("measures") or 0)
    x0, x1, unit = float(system["min_x"]), float(system["max_x"]), float(system.get("unit") or 1.0)
    inner = [float(b) for b in system.get("bars", []) if x0 + EDGE_UNITS * unit < b < x1 - EDGE_UNITS * unit]
    return n <= 0 or len(inner) != n - 1


def make_layout(geometry: dict, review: dict, measure_count: int) -> dict:
    """`review` is what `preprocess.review_image` returned (width, height, scale). `measure_count` is
    the number of measures in the final score; when the systems' counts do not add up to it, the
    measure indices are spread proportionally so every measure still has a system."""
    chain = geometry.get("chain") or {"resize": [1.0, 1.0], "crop": [0, 0], "scale": 1.0}
    s = float(review.get("scale") or 1.0)

    def rv(x: float, y: float) -> tuple[float, float]:
        ux, uy = to_upload(chain, x, y)
        return round(ux * s, 1), round(uy * s, 1)

    systems_in = geometry.get("systems", [])
    staves_in = geometry.get("staves", [])
    systems = []
    for i, first, n, bounds in system_spans(geometry, measure_count):
        sy = systems_in[i]
        staves = [st for st in staves_in if st.get("system") == i] or [sy]
        top = min(float(st["top_y"]) for st in staves)
        bottom = max(float(st.get("bottom_y", st["top_y"] + 4 * st.get("unit", 10))) for st in staves)
        left, _ = rv(bounds[0], top)
        right, _ = rv(bounds[-1], top)
        _, top_r = rv(bounds[0], top)
        _, bottom_r = rv(bounds[0], bottom)
        systems.append({
            "index": i, "x0": left, "x1": right, "top": top_r, "bottom": bottom_r,
            "unit": round(float(sy.get("unit") or 0) * (chain["resize"][1] and 1 / chain["resize"][1] / (chain["scale"] or 1.0)) * s, 2),
            "staves": [{"top": rv(bounds[0], float(st["top_y"]))[1], "bottom": rv(bounds[0], float(st.get("bottom_y", st["top_y"])))[1]} for st in staves],
            "measures": [{"index": first + k, "x0": rv(bounds[k], top)[0], "x1": rv(bounds[k + 1], top)[0]} for k in range(n)],
        })
    return {"width": review.get("width"), "height": review.get("height"), "systems": systems}
