"""`testomation` command line. Every command is a stub until its phase lands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from testomation import __version__

# command → (help, phase it arrives in; see docs/ROADMAP.md)
COMMANDS: dict[str, tuple[str, str]] = {
    "run": ("run the pipeline: scope, execute approved specs, triage, generate, report", "1"),
    "import": ("triage an existing Playwright project's JSON report", "2"),
    "review": ("decide open review items", "5"),
    "approve": ("promote draft specs to approved", "3"),
    "bench": ("score Testomation on the seeded-bug benchmark", "0"),
    "explore": ("run an exploratory session (LangGraph loop)", "6"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testomation", description="Autonomous, local-first software testing."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    run = sub.add_parser("run", help=COMMANDS["run"][0])
    run.add_argument("--pr", help="pull request number (run id: run-<pr>-<sha>)")

    imp = sub.add_parser("import", help=COMMANDS["import"][0])
    imp.add_argument("report", help="path to a Playwright JSON report")

    sub.add_parser("review", help=COMMANDS["review"][0])
    sub.add_parser("approve", help=COMMANDS["approve"][0])

    bench = sub.add_parser("bench", help=COMMANDS["bench"][0])
    bench.add_argument("--replay", action="store_true", help="replay tier: analyzer only")

    explore = sub.add_parser("explore", help=COMMANDS["explore"][0])
    explore.add_argument("--budget", default="15m", help="wall-clock budget, e.g. 15m")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    _, phase = COMMANDS[args.command]
    print(f"testomation {args.command}: not implemented yet (arrives in phase {phase})",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
