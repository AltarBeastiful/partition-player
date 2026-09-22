"""Command line: `partition-player recognize <file> -o <dir>` and `partition-player serve`.

`recognize` takes the same two kinds of page the API does: a photo, which the engine reads, or a
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

    rec = sub.add_parser("recognize", help="read one page: a photo, or a MusicXML file to open as it is")
    rec.add_argument("file", type=Path)
    rec.add_argument("-o", "--out", type=Path, default=None, help="output directory (default: <file>.out)")
    rec.add_argument("--engine", default=None, help="override PP_ENGINE (homr, audiveris, fake)")

    srv = sub.add_parser("serve", help="run the web app")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    if args.cmd == "recognize":
        from dataclasses import replace

        from .pipeline.musicxml import ingest, looks_like_musicxml
        from .pipeline.run import recognize

        if args.engine:
            settings = replace(settings, engine=args.engine)
        out = args.out or args.file.with_suffix(args.file.suffix + ".out")

        def notify(stage: str, msg: str) -> None:
            print(f"[{stage}] {msg}", file=sys.stderr)

        if looks_like_musicxml(args.file.name, args.file.read_bytes()[:64]):
            result = ingest(args.file, out, notify)
        else:
            result = recognize(args.file, out, settings, notify)
        print(json.dumps(json.loads((out / "result.json").read_text()), indent=2), file=sys.stderr)
        print(result)
        return 0

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("partition_player.api:app", host=args.host, port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
