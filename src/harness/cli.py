"""The `harness` command. A thin shell over `harness.api`, which is where the behaviour lives.

The predecessor had no command line at all and drove everything through a skill calling
`uv run python -c "..."`. That is a lot of quoting for an agent to get right at every phase, and
the phase packs here name commands instead - `harness brief 2` is something a capture can show it
ran, which a Python one-liner is not.
"""

from __future__ import annotations

import argparse
import sys

from . import api


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="A build harness whose state is queryable and whose checks prove themselves.")
    parser.add_argument("-C", "--target", default=None,
                        help="the workspace. Never defaults to the current directory.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("detect", help="what this workspace appears to be built with (runs nothing)")
    sub.add_parser("status", help="where the run is, in one screen")
    sub.add_parser("inherit", help="adopt what a previous run proved; re-run what is cheap")
    sub.add_parser("archive", help="fold this run into the workspace's memory")
    sub.add_parser("render", help="regenerate the read-only human views")
    sub.add_parser("selftest", help="has every check been seen to reject its own bad input?")
    sub.add_parser("score", help="grade this workspace against what can actually be checked")

    one = sub.add_parser("brief", help="what one phase is handed - a slice, not the document")
    one.add_argument("phase", type=int)

    start = sub.add_parser("start", help="scaffold a run: 4 fixed phases plus build slices")
    start.add_argument("run")
    start.add_argument("--slices", type=int, default=2)
    start.add_argument("--project", default="")

    checker = sub.add_parser("check", help="the checks; the exit code is the defect count")
    checker.add_argument("--checks", default=None,
                         help="comma-separated subset, e.g. state,memory,ignore")
    checker.add_argument("--run", default=None)

    imp = sub.add_parser("import", help="read an old harness workspace's memory")
    imp.add_argument("source")

    return parser


def _speak_utf8() -> None:
    """Make stdout survive the content.

    A Windows console is cp1252 by default, and a report that quotes a tree's own text will
    eventually carry an arrow, an em-dash or a non-Latin name. `print` then raises
    UnicodeEncodeError and the command dies having done its work - which is a report that fails
    on its own output, the same shape as a check that cannot fail. Found by exactly that: an
    imported archive row containing U+2192.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv=None) -> int:
    _speak_utf8()
    args = build_parser().parse_args(argv)
    target = args.target

    if args.command == "detect":
        return api.show(api.detect(target))
    if args.command == "status":
        return api.show(api.status(target))
    if args.command == "brief":
        return api.show(api.brief(target, args.phase))
    if args.command == "start":
        return api.show(api.start_run(target, args.run, slices=args.slices,
                                      project=args.project))
    if args.command == "check":
        names = [n.strip() for n in args.checks.split(",")] if args.checks else None
        return api.show(api.check(target, args.run, names))
    if args.command == "inherit":
        return api.show(api.inherit(target))
    if args.command == "archive":
        return api.show(api.archive(target))
    if args.command == "import":
        return api.show(api.import_workspace(target, args.source))
    if args.command == "render":
        return api.show(api.render(target))
    if args.command == "score":
        return api.show(api.scorecard(target))
    if args.command == "selftest":
        return api.show(api.selftest())
    return 1


if __name__ == "__main__":
    sys.exit(main())
