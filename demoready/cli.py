"""Command-line interface entry point for DemoReady."""

import argparse
from pathlib import Path
import sys

from demoready import __version__
from demoready.core.models import CheckStatus
from demoready.core.runner import run_inspection
from demoready.formatters.console import format_console_report
from demoready.formatters.json_formatter import format_json_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="demoready",
        description="DemoReady: Verify whether Node.js projects are ready to run and demonstrate.",
    )
    parser.add_argument(
        "-p",
        "--path",
        type=str,
        default=".",
        help="Path to the Node.js project directory (defaults to current working directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in structured JSON format.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Opt-in flag: execute `npm test` against the project. (Disabled by default for safety).",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=30,
        help="Timeout in seconds for test execution when --run-tests is enabled (default: 30s).",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    target_dir = Path(args.path)

    report = run_inspection(
        target_path=target_dir,
        run_tests=args.run_tests,
        test_timeout=args.test_timeout,
    )

    if args.json:
        print(format_json_report(report))
    else:
        print(format_console_report(report))

    # Exit with code 1 if any check failed; 0 otherwise
    if report.summary.get(CheckStatus.FAIL.value, 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
