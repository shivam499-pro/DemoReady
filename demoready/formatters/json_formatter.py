"""JSON formatter for machine-readable DemoReady reports."""

import json
from demoready.core.models import InspectionReport


def format_json_report(report: InspectionReport, indent: int = 2) -> str:
    """Serialize inspection report to JSON string with strictly sanitized fields."""
    return json.dumps(report.to_dict(), indent=indent)
