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
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write JSON report to the specified file path (implies --json).",
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

    if args.test_timeout <= 0:
        parser.error("--test-timeout must be a positive integer.")

    target_dir = Path(args.path)

    report = run_inspection(
        target_path=target_dir,
        run_tests=args.run_tests,
        test_timeout=args.test_timeout,
    )

    readiness_exit = 1 if report.summary.get(CheckStatus.FAIL.value, 0) > 0 else 0

    if args.output:
        output_path = Path(args.output)
        if output_path.exists() and output_path.is_dir():
            print(f"error: --output path is a directory: {output_path}", file=sys.stderr)
            return 2
        if not output_path.parent.exists() or not output_path.parent.is_dir():
            print(f"error: output directory does not exist: {output_path.parent}", file=sys.stderr)
            return 2
        try:
            json_text = format_json_report(report)
            output_path.write_text(json_text + "\n", encoding="utf-8")
            print(f"Report written to: {output_path}", file=sys.stderr)
        except OSError as e:
            err_msg = e.strerror if getattr(e, "strerror", None) else str(e)
            print(f"error: could not write report to {output_path}: {err_msg}", file=sys.stderr)
            return 2
        return readiness_exit

    if args.json:
        print(format_json_report(report))
    else:
        print(format_console_report(report))

    return readiness_exit


if __name__ == "__main__":
    sys.exit(main())
