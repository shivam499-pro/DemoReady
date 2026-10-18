"""Test command configuration and safe opt-in execution checks."""

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from demoready.core.models import CheckResult, CheckStatus


DEFAULT_PLACEHOLDER_SUBSTRINGS = [
    'echo "error: no test specified" && exit 1',
    "no test specified",
    "no tests specified",
    "not configured",
]

EXACT_DUMMY_COMMANDS = {
    "exit 1",
    "exit 0",
    "false",
    "true",
    ":",
}


def is_placeholder_test(command: str) -> bool:
    cleaned = command.strip().lower()
    return (
        any(p in cleaned for p in DEFAULT_PLACEHOLDER_SUBSTRINGS)
        or cleaned in EXACT_DUMMY_COMMANDS
        or not cleaned
    )


def check_test_script_configuration(pkg_data: Optional[Dict[str, Any]]) -> CheckResult:
    """Evaluate test script definition in package.json."""
    if not pkg_data:
        return CheckResult(
            name="Test Script Configuration",
            category="testing",
            status=CheckStatus.FAIL,
            message="Cannot check test command: package.json is missing or could not be parsed.",
            fix="Ensure valid package.json exists.",
        )

    scripts = pkg_data.get("scripts", {})
    if not isinstance(scripts, dict) or "test" not in scripts:
        return CheckResult(
            name="Test Script Configuration",
            category="testing",
            status=CheckStatus.WARNING,
            message="No 'test' script defined in package.json scripts.",
            fix="Add a 'test' script in package.json (e.g. \"test\": \"vitest run\" or \"test\": \"jest\").",
        )

    test_cmd = str(scripts["test"]).strip()
    if is_placeholder_test(test_cmd):
        return CheckResult(
            name="Test Script Configuration",
            category="testing",
            status=CheckStatus.FAIL,
            message=f"Placeholder test script detected: \"{test_cmd}\".",
            fix="Configure a real test runner instead of the npm default placeholder.",
            # scripts.test key was confirmed present and inspected.
            source_location={"file": "package.json", "field": "scripts.test"},
            details={"configured_command": test_cmd},
        )

    return CheckResult(
        name="Test Script Configuration",
        category="testing",
        status=CheckStatus.PASS,
        message=f"Configured test command: \"{test_cmd}\".",
        # scripts.test key was confirmed present and inspected.
        source_location={"file": "package.json", "field": "scripts.test"},
        details={"configured_command": test_cmd},
    )


def execute_test_command(target_path: Path, timeout_seconds: int = 30) -> CheckResult:
    """
    Safely execute npm test in target directory only when explicitly requested.
    Enforces timeout and captures exit status without leaking secrets.
    """
    npm_bin = shutil.which("npm.cmd") if shutil.which("npm.cmd") else shutil.which("npm")
    if not npm_bin:
        return CheckResult(
            name="Test Command Execution",
            category="testing",
            status=CheckStatus.FAIL,
            message="npm executable was not found on system PATH.",
            fix="Install Node.js/npm and ensure it is available on system PATH.",
        )

    try:
        proc = subprocess.run(
            [npm_bin, "test"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            # Never inherit unsanitized sensitive overrides
        )

        exit_code = proc.returncode
        if exit_code == 0:
            return CheckResult(
                name="Test Command Execution",
                category="testing",
                status=CheckStatus.PASS,
                message=f"Test command executed successfully (exit code {exit_code}).",
                details={"exit_code": exit_code},
            )
        else:
            return CheckResult(
                name="Test Command Execution",
                category="testing",
                status=CheckStatus.FAIL,
                message=f"Test command failed with exit code {exit_code}.",
                fix="Run `npm test` locally in the project directory to inspect and resolve test failures.",
                details={"exit_code": exit_code},
            )

    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Test Command Execution",
            category="testing",
            status=CheckStatus.FAIL,
            message=f"Test command timed out after {timeout_seconds} seconds.",
            fix="Optimize slow tests or increase the timeout using --test-timeout.",
            details={"timeout_seconds": timeout_seconds},
        )
    except Exception as err:
        return CheckResult(
            name="Test Command Execution",
            category="testing",
            status=CheckStatus.FAIL,
            message=f"Failed to execute test command: {type(err).__name__}",
            fix="Check permissions and verify that npm can be executed in the target directory.",
        )


def run_tests_checks(
    target_path: Path,
    pkg_data: Optional[Dict[str, Any]],
    run_tests: bool = False,
    test_timeout: int = 30,
) -> List[CheckResult]:
    """Run test configuration check and optional opt-in test execution."""
    results: List[CheckResult] = []

    config_result = check_test_script_configuration(pkg_data)
    results.append(config_result)

    if not run_tests:
        results.append(
            CheckResult(
                name="Test Command Execution",
                category="testing",
                status=CheckStatus.NOT_CHECKED,
                message="Test execution skipped by default. Provide --run-tests to execute.",
            )
        )
    else:
        # If test configuration failed (e.g. placeholder or missing), do not run
        if config_result.status == CheckStatus.FAIL:
            results.append(
                CheckResult(
                    name="Test Command Execution",
                    category="testing",
                    status=CheckStatus.FAIL,
                    message="Refusing to execute: test command is invalid or a placeholder.",
                    fix=config_result.fix,
                )
            )
        else:
            results.append(execute_test_command(target_path, timeout_seconds=test_timeout))

    return results
