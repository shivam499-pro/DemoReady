"""
Static endpoint detection and health check verification.

NOTE: Endpoint detection uses regex-based heuristics over source files, not a
full JavaScript AST parser. It looks for standard HTTP route strings (e.g.
'/health', '/status', '/api/health') and file-based route conventions.
Dynamic route construction, variable interpolation, or non-standard routing
decorators may not be detected by this heuristic.
"""

from pathlib import Path
import re
from typing import List, Optional, Tuple

from demoready.core.models import CheckResult, CheckStatus
from demoready.core.classifier import ProjectType


# Project types for which HTTP health endpoints are not applicable.
_NO_HEALTH_ENDPOINT_TYPES = frozenset({
    ProjectType.REUSABLE_LIBRARY,
    ProjectType.CLI_TOOL,
    ProjectType.MONOREPO_ROOT,
})



IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "test",
    "tests",
    "__tests__",
    "__test__",
    "spec",
    "specs",
}

SOURCE_EXTENSIONS = {".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx"}


def is_test_file(filename: str) -> bool:
    """
    Check if a filename is an identifiable test or spec file.
    Matches:
    - Root test files: test.js, spec.ts, tests.js, specs.ts
    - Prefix-style test files: test_health.js, test-health.ts, spec_auth.js, spec-auth.ts
    - Suffix-style test files: health_test.ts, health-test.js, user_spec.ts
    - Standard dot-test/dot-spec patterns: *.test.*, *.spec.*
    Preserves regular production files like contest.js, protest.ts, special.ts, health.js.
    """
    lower = filename.lower()
    # Keep the existing .test.* and .spec.* filtering in place
    if ".test." in lower or ".spec." in lower:
        return True

    stem = lower.rsplit(".", 1)[0]
    # 1. Exact match for test / spec base names (e.g. test.js, spec.ts)
    if stem in ("test", "spec", "tests", "specs"):
        return True
    # 2. Prefix-style test files (e.g. test_health.js, test-health.ts, spec_auth.js)
    if stem.startswith(("test_", "test-", "spec_", "spec-")):
        return True
    # 3. Suffix-style test files (e.g. health_test.ts, api-test.js)
    if stem.endswith(("_test", "-test", "_spec", "-spec", "_tests", "-tests", "_specs", "-specs")):
        return True
    return False


HEALTH_ROUTE_PATTERN = re.compile(
    r"""['"`]/(?:api/(?:v[0-9]+/)?|v[0-9]+/)?(?:health|healthz|status|live|ready|ping)/?['"`]""",
    re.IGNORECASE,
)

GENERAL_API_PATTERN = re.compile(
    r"""(?:app\.(?:get|post|put|delete|use)|router\.(?:get|post|put|delete|use)|['"`]/api/)""",
    re.IGNORECASE,
)


def scan_source_files(target_path: Path, max_files: int = 150) -> Tuple[List[str], bool, bool]:
    """
    Safely scan project source files for endpoint patterns without executing code.
    Returns: (matching_health_files, has_general_api_routes, has_source_files)
    """
    health_matches: List[str] = []
    has_general_api = False
    files_scanned = 0

    # Also check file-based routing: e.g. src/app/api/health/route.ts or routes/health.ts
    for file_path in target_path.rglob("*"):
        # Skip ignored directories (including test and spec directories)
        if any(part.lower() in IGNORED_DIRECTORIES for part in file_path.parts):
            continue

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue

        # Skip identifiable test files even if located in source directories (e.g., src/test_health.js)
        if is_test_file(file_path.name):
            continue

        files_scanned += 1
        rel_str = str(file_path.relative_to(target_path)).replace("\\", "/")

        # Check for health file path
        if re.search(r"(?:^|/)(?:api/)?(?:health|healthz|status|ready|live)(?:/route)?\.[jt]sx?$", rel_str, re.IGNORECASE):
            health_matches.append(rel_str)
            has_general_api = True
            continue

        try:
            # Read first 64KB max to prevent scanning huge minified files
            content = file_path.read_text(encoding="utf-8", errors="ignore")[:65536]
            if HEALTH_ROUTE_PATTERN.search(content):
                health_matches.append(rel_str)
            if not has_general_api and GENERAL_API_PATTERN.search(content):
                has_general_api = True
        except Exception:
            continue

        if files_scanned >= max_files:
            break

    return health_matches, has_general_api, files_scanned > 0


def run_endpoints_checks(
    target_path: Path,
    project_type: Optional[ProjectType] = None,
) -> List[CheckResult]:
    """
    Run static endpoint checks and record honest status.
    Explicitly labels static detection separately from live verification.
    """
    if project_type in _NO_HEALTH_ENDPOINT_TYPES:
        type_label = project_type.value.replace("_", " ").title()
        return [
            CheckResult(
                name="Static Health Endpoint Definition",
                category="endpoints",
                status=CheckStatus.NOT_APPLICABLE,
                message=(
                    f"Health endpoint checks are not applicable to {type_label} "
                    f"projects (not a persistent web service or application)."
                ),
            ),
            CheckResult(
                name="Live Endpoint Verification",
                category="endpoints",
                status=CheckStatus.NOT_APPLICABLE,
                message=(
                    f"Live endpoint verification is not applicable to {type_label} "
                    f"projects."
                ),
            ),
        ]

    results: List[CheckResult] = []

    health_files, has_general_api, has_sources = scan_source_files(target_path)

    if health_files:
        sample_file = health_files[0]
        results.append(
            CheckResult(
                name="Static Health Endpoint Definition",
                category="endpoints",
                status=CheckStatus.PASS,
                message=(
                    f"Static health route pattern detected in {sample_file} (heuristic match). "
                    "Note: This is static code detection only and does not verify runtime availability or HTTP response."
                ),
                # Exact relative path of the matched source file.
                # Detection was via regex heuristic only — not a full AST parse.
                source_location={"file": sample_file},
                details={
                    "matching_files": health_files[:5],
                    "detection_type": "static_regex_heuristic",
                },
            )
        )
    elif has_general_api:
        results.append(
            CheckResult(
                name="Static Health Endpoint Definition",
                category="endpoints",
                status=CheckStatus.WARNING,
                message="General API/server routes detected, but no dedicated /health, /status, or /ping route was found.",
                fix="Add a dedicated health check endpoint (e.g., GET /health or GET /api/health) to confirm service readiness.",
            )
        )
    elif has_sources:
        results.append(
            CheckResult(
                name="Static Health Endpoint Definition",
                category="endpoints",
                status=CheckStatus.NOT_CHECKED,
                message="No server framework or HTTP routes detected in scanned source files.",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Static Health Endpoint Definition",
                category="endpoints",
                status=CheckStatus.NOT_CHECKED,
                message="No JavaScript/TypeScript source files found to scan for endpoints.",
            )
        )

    # Always present a distinct Live Endpoint Verification check to be completely transparent
    results.append(
        CheckResult(
            name="Live Endpoint Verification",
            category="endpoints",
            status=CheckStatus.NOT_CHECKED,
            message="Live endpoint verification skipped. Static analysis cannot guarantee server availability without running a live server probe.",
        )
    )

    return results
