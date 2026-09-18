"""Command line: `partition-player recognize <image> -o <dir>` and `partition-player serve`."""
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

    rec = sub.add_parser("recognize", help="run the pipeline on one image")
    rec.add_argument("image", type=Path)
    rec.add_argument("-o", "--out", type=Path, default=None, help="output directory (default: <image>.out)")
    rec.add_argument("--engine", default=None, help="override PP_ENGINE (homr, audiveris, fake)")

    srv = sub.add_parser("serve", help="run the web app")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    if args.cmd == "recognize":
        from dataclasses import replace

        from .pipeline.run import recognize

        if args.engine:
            settings = replace(settings, engine=args.engine)
        out = args.out or args.image.with_suffix(args.image.suffix + ".out")
        result = recognize(args.image, out, settings, lambda stage, msg: print(f"[{stage}] {msg}", file=sys.stderr))
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
