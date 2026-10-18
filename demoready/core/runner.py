"""Orchestrator for DemoReady checks."""

from pathlib import Path

from demoready.checks.endpoints import run_endpoints_checks
from demoready.checks.environment import run_environment_checks
from demoready.checks.files import run_files_checks
from demoready.checks.tests_config import run_tests_checks
from demoready.core.classifier import classify_project
from demoready.core.models import CheckResult, InspectionReport


def run_inspection(
    target_path: Path,
    run_tests: bool = False,
    test_timeout: int = 30,
) -> InspectionReport:
    """
    Run the full suite of DemoReady checks against target_path.
    Guarantees:
    - Never mutates or modifies the scanned repository.
    - Never executes npm install or unapproved commands.
    - Never runs test scripts unless run_tests=True.
    - Strictly hides secret values.
    """
    resolved_path = target_path.resolve()
    all_results: list[CheckResult] = []

    # 1. Files & project structure
    file_results, pkg_data = run_files_checks(resolved_path)
    all_results.extend(file_results)

    # If the directory doesn't exist or isn't a directory, halt early
    if not resolved_path.exists() or not resolved_path.is_dir():
        return InspectionReport(target_path=str(resolved_path), results=all_results)

    # 2. Project classification
    classification = classify_project(resolved_path, pkg_data)
    project_type = classification.project_type

    # 3. Environment checks (context-aware based on project type)
    env_results = run_environment_checks(resolved_path, project_type=project_type)
    all_results.extend(env_results)

    # 4. Static endpoint checks (context-aware based on project type)
    endpoint_results = run_endpoints_checks(resolved_path, project_type=project_type)
    all_results.extend(endpoint_results)

    # 5. Test configuration & optional opt-in execution
    test_results = run_tests_checks(
        resolved_path,
        pkg_data=pkg_data,
        run_tests=run_tests,
        test_timeout=test_timeout,
    )
    all_results.extend(test_results)

    return InspectionReport(
        target_path=str(resolved_path),
        results=all_results,
        project_type=project_type.value,
    )
