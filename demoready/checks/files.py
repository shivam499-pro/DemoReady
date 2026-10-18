"""Required files and Node.js project structure checks."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from demoready.core.models import CheckResult, CheckStatus


KNOWN_LOCKFILES = [
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
]


def validate_target_directory(target_path: Path) -> Optional[CheckResult]:
    """Validate that the target path exists and is a directory."""
    if not target_path.exists():
        return CheckResult(
            name="Target Path Validation",
            category="filesystem",
            status=CheckStatus.FAIL,
            message=f"Target path does not exist: {target_path}",
            fix="Provide a valid existing directory path via --path.",
        )
    if not target_path.is_dir():
        return CheckResult(
            name="Target Path Validation",
            category="filesystem",
            status=CheckStatus.FAIL,
            message=f"Target path is a file, not a directory: {target_path}",
            fix="Provide the path to the root directory of the project.",
        )
    return None


def read_package_json(target_path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[CheckResult]]:
    """Safely read and parse package.json from target directory."""
    pkg_file = target_path / "package.json"
    if not pkg_file.exists():
        return None, CheckResult(
            name="package.json Presence",
            category="required_files",
            status=CheckStatus.FAIL,
            message="Missing required package.json in target directory.",
            fix="Run `npm init -y` or ensure --path points to the root of a Node.js project.",
        )

    try:
        content = pkg_file.read_text(encoding="utf-8")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None, CheckResult(
                name="package.json Structure",
                category="required_files",
                status=CheckStatus.FAIL,
                message="package.json root content must be a JSON object.",
                fix="Format package.json as a valid JSON object.",
            )
        return parsed, CheckResult(
            name="package.json Validity",
            category="required_files",
            status=CheckStatus.PASS,
            message=f"Valid package.json found (project: {parsed.get('name', 'unnamed')}, version: {parsed.get('version', 'unknown')}).",
            # package.json was confirmed present and parsed; location is factual.
            source_location={"file": "package.json"},
            details={
                "name": parsed.get("name"),
                "version": parsed.get("version"),
            },
        )
    except json.JSONDecodeError as err:
        return None, CheckResult(
            name="package.json Syntax",
            category="required_files",
            status=CheckStatus.FAIL,
            message=f"package.json is malformed: JSON parsing error at line {err.lineno}, column {err.colno}.",
            fix="Correct JSON syntax errors in package.json.",
        )
    except Exception as err:
        return None, CheckResult(
            name="package.json Read",
            category="required_files",
            status=CheckStatus.FAIL,
            message=f"Unable to read package.json: {str(err)}",
            fix="Check file permissions for package.json.",
        )


def check_lockfile(target_path: Path) -> CheckResult:
    """Check for lockfile existence."""
    found_lockfiles = [lf for lf in KNOWN_LOCKFILES if (target_path / lf).exists()]
    if found_lockfiles:
        return CheckResult(
            name="Lockfile Presence",
            category="required_files",
            status=CheckStatus.PASS,
            message=f"Lockfile detected: {', '.join(found_lockfiles)}.",
            details={"lockfiles": found_lockfiles},
        )
    return CheckResult(
        name="Lockfile Presence",
        category="required_files",
        status=CheckStatus.WARNING,
        message="No lockfile detected (package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lockb).",
        fix="Generate a lockfile using your package manager (e.g., `npm install`).",
    )


def check_node_modules(target_path: Path) -> CheckResult:
    """Check for node_modules presence."""
    modules_dir = target_path / "node_modules"
    if modules_dir.exists() and modules_dir.is_dir():
        return CheckResult(
            name="Dependencies Directory",
            category="required_files",
            status=CheckStatus.PASS,
            message="node_modules directory found.",
        )
    return CheckResult(
        name="Dependencies Directory",
        category="required_files",
        status=CheckStatus.WARNING,
        message="node_modules directory is missing.",
        fix="Run `npm install` to install required dependencies.",
    )


def run_files_checks(target_path: Path) -> Tuple[List[CheckResult], Optional[Dict[str, Any]]]:
    """Run all required file and structure checks."""
    results: List[CheckResult] = []

    path_error = validate_target_directory(target_path)
    if path_error:
        results.append(path_error)
        return results, None

    pkg_data, pkg_result = read_package_json(target_path)
    if pkg_result:
        results.append(pkg_result)

    if pkg_data is None:
        # Cannot meaningfully continue file checks if package.json is missing or invalid
        return results, None

    results.append(check_lockfile(target_path))
    results.append(check_node_modules(target_path))
    return results, pkg_data
