"""Command line: `partition-player recognize <file> -o <dir>` and `partition-player serve`.

`recognize` takes the same three kinds of page the API does: a photo, which the engine reads, a PDF,
whose pages are rendered and read one by one (plan 0012), or a
MusicXML file, which is opened as it is (plan 0010)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="partition-player")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("recognize", help="read a page: a photo, a PDF, or a MusicXML file to open as it is")
    rec.add_argument("file", type=Path)
    rec.add_argument("-o", "--out", type=Path, default=None, help="output directory (default: <file>.out)")
    rec.add_argument("--engine", default=None, help="override PP_ENGINE (homr, audiveris, fake)")

    srv = sub.add_parser("serve", help="run the web app")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    mp = sub.add_parser("model-pass", help="the model pass through your own Claude Code session, no API key (ADR 0010)")
    mps = mp.add_subparsers(dest="mp_cmd", required=True)
    exp = mps.add_parser("export", help="write one repair bundle per span for a Claude Code session to answer")
    exp.add_argument("job")
    exp.add_argument("-o", "--out", type=Path, default=None, help="bundle directory (default: ./model-pass-<job>)")
    exp.add_argument("--span", action="append", default=[], metavar="STAFF:FROM:TO[:WORDSFILE]",
                     help="a span, measures counted from 0 and inclusive; repeat for several. With a text file of words "
                          "(verses separated by a blank line) the words are placed; without, notes and chords are checked")
    exp.add_argument("--note", default="", help="what is known about a span without words (one sentence)")
    imp = mps.add_parser("import", help="validate the answers a Claude Code session wrote and store them as a draft")
    imp.add_argument("job")
    imp.add_argument("answers", type=Path)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    if args.cmd == "recognize":
        from dataclasses import replace

        from .pipeline.musicxml import ingest, looks_like_musicxml
        from .pipeline.pages import read_pdf
        from .pipeline.pdf import looks_like_pdf
        from .pipeline.run import recognize

        if args.engine:
            settings = replace(settings, engine=args.engine)
        out = args.out or args.file.with_suffix(args.file.suffix + ".out")

        def notify(stage: str, msg: str) -> None:
            print(f"[{stage}] {msg}", file=sys.stderr)

        head = args.file.read_bytes()[:64]
        if looks_like_musicxml(args.file.name, head):
            result = ingest(args.file, out, notify)
        elif looks_like_pdf(head):
            result = read_pdf(args.file, out, settings, notify)
        else:
            result = recognize(args.file, out, settings, notify)
        print(json.dumps(json.loads((out / "result.json").read_text()), indent=2), file=sys.stderr)
        print(result)
        return 0

    if args.cmd == "model-pass":
        return _model_pass(args, settings)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("partition_player.api:app", host=args.host, port=args.port)
        return 0
    return 1


def _model_pass(args, settings) -> int:
    from .jobs import JobStore
    from .model import claude_code, lyrics_pass
    from . import review

    store = JobStore(settings)
    job = store.get(args.job)
    if job is None or job.status != "done":
        print(f"no finished score with the id {args.job!r}", file=sys.stderr)
        return 1
    d = store.dir(args.job)
    if args.mp_cmd == "export":
        spans = []
        for text in args.span:
            try:
                staff, first, last, *rest = text.split(":", 3)
                staff, first, last = int(staff), int(first), int(last)
                words = Path(rest[0]).read_text() if rest else ""
            except (ValueError, OSError) as e:
                print(f"--span wants STAFF:FROM:TO[:WORDSFILE], got {text!r} ({e})", file=sys.stderr)
                return 1
            spans.append({"staff": staff, "from": first, "to": last, "lyrics_source": words, "note": args.note})
        if not spans:
            print("give at least one --span STAFF:FROM:TO", file=sys.stderr)
            return 1
        out = args.out or Path(f"model-pass-{args.job}")
        try:
            index = claude_code.export_bundles(d, spans, out)
        except lyrics_pass.SpanError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"{len(index['tasks'])} bundle(s) in {out}; let your Claude Code session answer them, then: "
              f"partition-player model-pass import {args.job} <answers.json>")
        return 0
    try:
        answers = json.loads(args.answers.read_text())
        if not isinstance(answers, dict):
            raise ValueError("the file is not an object")
    except (OSError, ValueError) as e:
        print(f"cannot read {args.answers}: {e}", file=sys.stderr)
        return 1
    with store.lock:
        draft = claude_code.import_answers(d, answers, review.load(d)["revision"])
    print(f"draft stored: {len(draft['changes'])} change(s), {len(draft['dropped'])} dropped; open the score and apply it in Check with a model")
    for x in draft["dropped"]:
        print(f"dropped (measures {x['span']['from'] + 1} to {x['span']['to'] + 1}): {x['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
