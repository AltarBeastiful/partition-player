#!/usr/bin/env python3
"""Talk to a partition-player site for the model pass (ADR 0010, the Claude Code route). Standard library only.

  pp.py fetch  <score url or id> [--span STAFF:FROM:TO[:WORDSFILE]]... [--note TEXT] [-o DIR]
  pp.py submit <score url or id> <answers.json>

A score url looks like https://host/s/<id>. A bare id needs PP_URL (the site's address). When the site has a token,
put it in PP_API_TOKEN. Measures are counted from 0 and inclusive. Without --span, the spans are the engine's doubts.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def parse_target(target: str, env: dict | None = None) -> tuple[str, str]:
    """(site base url, job id) from a score url, or from a bare id and PP_URL."""
    env = os.environ if env is None else env
    m = re.match(r"^(https?://[^/]+)/s/([A-Za-z0-9]+)/?(?:[?#].*)?$", target.strip())
    if m:
        return m.group(1), m.group(2)
    if re.fullmatch(r"[A-Za-z0-9]+", target.strip()) and env.get("PP_URL"):
        return env["PP_URL"].rstrip("/"), target.strip()
    raise SystemExit("give a score url like https://host/s/<id>, or a bare id with PP_URL set to the site's address")


def call(method: str, url: str, body: dict | None = None, binary: bool = False):
    headers = {"Content-Type": "application/json", "User-Agent": "partition-player-skill"}
    if os.environ.get("PP_API_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['PP_API_TOKEN']}"
    req = urllib.request.Request(url, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except ValueError:
            pass
        raise SystemExit(f"{method} {url}: {e.code} {detail}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"{method} {url}: {e.reason}") from e
    return data if binary else json.loads(data)


def parse_spans(texts: list[str], note: str) -> list[dict]:
    spans = []
    for text in texts:
        try:
            staff, first, last, *rest = text.split(":", 3)
            span = {"staff": int(staff), "from": int(first), "to": int(last)}
            if rest:
                span["lyrics_source"] = Path(rest[0]).read_text()
        except (ValueError, OSError) as e:
            raise SystemExit(f"--span wants STAFF:FROM:TO[:WORDSFILE], got {text!r} ({e})") from e
        if note and "lyrics_source" not in span:
            span["note"] = note
        spans.append(span)
    return spans


def fetch(args) -> int:
    base, job = parse_target(args.target)
    out = call("POST", f"{base}/api/jobs/{job}/model-pass/export", {"spans": parse_spans(args.span, args.note)})
    d = Path(args.out or f"model-pass-{job}")
    d.mkdir(parents=True, exist_ok=True)
    page = None
    if out.get("page"):
        page = d / "page.webp"
        page.write_bytes(call("GET", base + out["page"], binary=True))
    index = []
    for t in out["tasks"]:
        td = d / t["id"]
        td.mkdir(exist_ok=True)
        (td / "prompt.txt").write_text(t["prompt"])
        (td / "task.json").write_text(json.dumps({"span": t["span"], "verse": t["verse"], "answer_format": t["answer_format"]}, ensure_ascii=False, indent=1))
        (td / "score.musicxml").write_text(t["score_musicxml"])
        index.append({"dir": t["id"], "span": t["span"], "verse": t["verse"]})
    (d / "index.json").write_text(json.dumps({"job": job, "site": base, "page": page.name if page else None, "tasks": index}, ensure_ascii=False, indent=1))
    print(f"{len(index)} task(s) written to {d}/ (page photo: {page or 'none'})")
    for t in index:
        s = t["span"]
        print(f"  {t['dir']}: staff {s['staff']} measures {s['from']}-{s['to']}" + (f" verse {t['verse']}" if t["verse"] else ""))
    return 0


def submit(args) -> int:
    base, job = parse_target(args.target)
    answers = json.loads(Path(args.answers).read_text())
    draft = call("POST", f"{base}/api/jobs/{job}/model-pass/import", answers)
    changes, dropped = draft.get("changes", []), draft.get("dropped", [])
    print(f"draft stored: {len(changes)} change(s), {len(dropped)} answer(s) dropped")
    for x in dropped:
        s = x.get("span", {})
        print(f"  dropped (staff {s.get('staff')} measures {s.get('from')}-{s.get('to')}): {x.get('reason')}")
    print(f"review it, then apply: {base}/s/{job}  (Check with a model -> the draft opens in the sheet)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("target")
    f.add_argument("--span", action="append", default=[])
    f.add_argument("--note", default="")
    f.add_argument("-o", "--out", default=None)
    s = sub.add_parser("submit")
    s.add_argument("target")
    s.add_argument("answers")
    args = p.parse_args(argv)
    return fetch(args) if args.cmd == "fetch" else submit(args)


if __name__ == "__main__":
    sys.exit(main())
