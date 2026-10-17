"""Console formatter for human-readable terminal reports."""

import os
import sys
from demoready.core.models import CheckStatus, InspectionReport


# ANSI color codes with automatic detection
SUPPORTS_COLOR = (
    sys.stdout.isatty()
    and not os.environ.get("NO_COLOR")
    and not os.environ.get("TERM") == "dumb"
)

COLORS = {
    CheckStatus.PASS: "\033[92m",        # Green
    CheckStatus.WARNING: "\033[93m",     # Yellow
    CheckStatus.FAIL: "\033[91m",        # Red
    CheckStatus.NOT_CHECKED: "\033[90m", # Dim / Gray
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "CYAN": "\033[96m",
}


def _colorize(text: str, color_key: str) -> str:
    if not SUPPORTS_COLOR:
        return text
    return f"{COLORS.get(color_key, '')}{text}{COLORS['RESET']}"


def format_console_report(report: InspectionReport) -> str:
    """Format an InspectionReport into a clean, human-readable console string."""
    lines: list[str] = []

    header = f"=== DemoReady Inspection: {report.target_path} ==="
    lines.append(_colorize(header, "BOLD"))
    lines.append("-" * len(header))

    for check in report.results:
        status_str = f"[{check.status.value}]".ljust(14)
        colored_status = _colorize(status_str, check.status)

        prefix = f"{colored_status} {check.name}: "
        lines.append(f"{prefix}{check.message}")

        if check.fix and check.status in (CheckStatus.WARNING, CheckStatus.FAIL):
            fix_line = f"              -> Fix: {check.fix}"
            lines.append(_colorize(fix_line, "CYAN"))

    lines.append("-" * len(header))

    summary = report.summary
    summary_parts = [
        f"{summary[CheckStatus.PASS.value]} PASS",
        f"{summary[CheckStatus.WARNING.value]} WARNING",
        f"{summary[CheckStatus.FAIL.value]} FAIL",
        f"{summary[CheckStatus.NOT_CHECKED.value]} NOT_CHECKED",
    ]
    lines.append(f"Summary: {', '.join(summary_parts)}")

    status = report.readiness_status
    if status == "READY":
        overall_badge = _colorize("[READY FOR DEMO]", CheckStatus.PASS)
    elif status == "READY_WITH_WARNINGS":
        overall_badge = _colorize("[READY WITH WARNINGS]", CheckStatus.WARNING)
    else:
        overall_badge = _colorize("[NOT READY FOR DEMO]", CheckStatus.FAIL)

    lines.append(f"Readiness: {overall_badge}")

    return "\n".join(lines)
