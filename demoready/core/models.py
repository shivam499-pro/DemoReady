"""Data models for DemoReady check results and inspection reports."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import datetime


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class CheckResult:
    name: str
    category: str
    status: CheckStatus
    message: str
    fix: Optional[str] = None
    # source_location identifies the file and/or field that was actually inspected
    # to produce this finding.  Values are filenames or field paths only — never
    # file contents, env values, or secrets.  Omit entirely when the source is
    # unknown or was not inspected (e.g. path-not-found errors).
    source_location: Optional[Dict[str, str]] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "category": self.category,
            "status": self.status.value,
            "message": self.message,
        }
        if self.fix:
            data["fix"] = self.fix
        # Serialize source_location only when present; values are paths/field
        # names — never secret values or file contents.
        if self.source_location is not None:
            data["source_location"] = self.source_location
        if self.details is not None:
            data["details"] = self.details
        return data


@dataclass
class InspectionReport:
    target_path: str
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    results: List[CheckResult] = field(default_factory=list)
    # Populated by the classifier in runner.py; None means classification was
    # not attempted (e.g. early exit due to missing directory).
    project_type: Optional[str] = None

    @property
    def summary(self) -> Dict[str, int]:
        counts = {
            CheckStatus.PASS.value: 0,
            CheckStatus.WARNING.value: 0,
            CheckStatus.FAIL.value: 0,
            CheckStatus.NOT_CHECKED.value: 0,
            CheckStatus.NOT_APPLICABLE.value: 0,
        }
        for r in self.results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return counts

    @property
    def readiness_status(self) -> str:
        if self.summary[CheckStatus.FAIL.value] > 0:
            return "NOT_READY"
        if self.summary[CheckStatus.WARNING.value] > 0:
            return "READY_WITH_WARNINGS"
        return "READY"

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "target_path": self.target_path,
            "timestamp": self.timestamp,
            "readiness_status": self.readiness_status,
        }
        if self.project_type is not None:
            data["project_type"] = self.project_type
        data["summary"] = self.summary
        data["checks"] = [r.to_dict() for r in self.results]
        return data
