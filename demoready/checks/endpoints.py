"""Static endpoint detection and health check verification."""

from pathlib import Path
import re
from typing import List, Optional, Tuple

from demoready.core.models import CheckResult, CheckStatus


IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
}

SOURCE_EXTENSIONS = {".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx"}

HEALTH_ROUTE_PATTERN = re.compile(
    r"""['"`]/(?:api/)?(?:health|healthz|status|live|ready|ping)['"`]""",
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
        # Skip ignored directories
        if any(part in IGNORED_DIRECTORIES for part in file_path.parts):
            continue

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
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


def run_endpoints_checks(target_path: Path) -> List[CheckResult]:
    """
    Run static endpoint checks and record honest status.
    Explicitly labels static detection separately from live verification.
    """
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
                    f"Static health route pattern detected in {sample_file}. "
                    "Note: This is static code detection only and does not verify runtime availability or HTTP response."
                ),
                details={"matching_files": health_files[:5]},
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
