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


@dataclass
class CheckResult:
    name: str
    category: str
    status: CheckStatus
    message: str
    fix: Optional[str] = None
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

    @property
    def summary(self) -> Dict[str, int]:
        counts = {
            CheckStatus.PASS.value: 0,
            CheckStatus.WARNING.value: 0,
            CheckStatus.FAIL.value: 0,
            CheckStatus.NOT_CHECKED.value: 0,
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
        return {
            "target_path": self.target_path,
            "timestamp": self.timestamp,
            "readiness_status": self.readiness_status,
            "summary": self.summary,
            "checks": [r.to_dict() for r in self.results],
        }
