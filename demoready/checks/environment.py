"""Environment variable checks with strict zero-secret leakage guarantees."""

from pathlib import Path
import re
from typing import List, Optional, Set

from demoready.core.models import CheckResult, CheckStatus
from demoready.core.classifier import ProjectType


ENV_TEMPLATE_CANDIDATES = [
    ".env.example",
    ".env.template",
    ".env.sample",
]

ENV_FILE_CANDIDATES = [
    ".env",
    ".env.local",
]

# Regex matches valid variable name definitions, e.g.:
# KEY=...
# "KEY"=... / 'KEY'=...
# export KEY=... / export "KEY"=...
# KEY (in template files)
# Ignores comments (#, //, ;) and empty lines
VAR_PATTERN = re.compile(
    r"""^\s*(?:export\s+)?["']?([A-Za-z_][A-Za-z0-9_]*)["']?(?:\s*=|\s*$)"""
)


def extract_variable_names(file_path: Path) -> Set[str]:
    """
    Safely extract ONLY variable names from an environment file.
    Under NO circumstance are variable values stored, captured, or returned.
    """
    if not file_path.exists() or not file_path.is_file():
        return set()

    var_names: Set[str] = set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "//", ";")):
                continue
            match = VAR_PATTERN.match(line)
            if match:
                # Capture the name group ONLY
                var_names.add(match.group(1))
    except Exception:
        # Never log or expose file content upon error
        return set()

    return var_names


def find_first_existing(target_path: Path, candidates: List[str]) -> Optional[Path]:
    for candidate in candidates:
        p = target_path / candidate
        if p.exists() and p.is_file():
            return p
    return None


def find_all_existing(target_path: Path, candidates: List[str]) -> List[Path]:
    existing: List[Path] = []
    for candidate in candidates:
        p = target_path / candidate
        if p.exists() and p.is_file():
            existing.append(p)
    return existing


def run_environment_checks(
    target_path: Path,
    project_type: Optional[ProjectType] = None,
) -> List[CheckResult]:
    """
    Evaluate environment configuration parity across layered environment files
    (.env, .env.local) without ever reading or revealing secret values.

    When ``project_type`` is supplied, context-aware suppression is applied:

    * REUSABLE_LIBRARY  -> NOT_APPLICABLE (libraries are configured by callers,
                           not by .env files).
    * CLI_TOOL / MONOREPO_ROOT -> NOT_APPLICABLE unless a template file exists
                           at the project root (presence of a template is
                           positive evidence that env vars are documented).
    * UNCLEAR with no env files at all -> NOT_CHECKED (insufficient evidence
                           to conclude env vars are required).
    * All other cases   -> existing checks, with Case-2 severity downgraded
                           from FAIL to WARNING (static inspection cannot prove
                           an app cannot run; vars may be supplied via system
                           environment or CI secrets).

    When ``project_type`` is None the function behaves as it did before the
    classifier was introduced, so existing tests that call the function directly
    remain unaffected.
    """
    template_path = find_first_existing(target_path, ENV_TEMPLATE_CANDIDATES)
    existing_env_files = find_all_existing(target_path, ENV_FILE_CANDIDATES)

    results: List[CheckResult] = []

    # ── Project-type applicability gates ────────────────────────────────────

    if project_type == ProjectType.REUSABLE_LIBRARY:
        results.append(
            CheckResult(
                name="Environment Configuration",
                category="environment",
                status=CheckStatus.NOT_APPLICABLE,
                message=(
                    "Environment variable checks are not applicable to reusable library "
                    "packages. Libraries are configured by their callers via options or "
                    "constructor arguments, not by .env files."
                ),
            )
        )
        return results

    if project_type in (ProjectType.CLI_TOOL, ProjectType.MONOREPO_ROOT):
        if not template_path:
            # No documented env requirements → skip.
            type_label = project_type.value.replace("_", " ").title()
            results.append(
                CheckResult(
                    name="Environment Configuration",
                    category="environment",
                    status=CheckStatus.NOT_APPLICABLE,
                    message=(
                        f"No environment template found. Environment variable checks are "
                        f"not applicable to {type_label} projects without a documented "
                        f"template (.env.example / .env.template / .env.sample)."
                    ),
                )
            )
            return results
        # Template exists → fall through to normal checks below.

    # ── UNCLEAR + no env artefacts at all ────────────────────────────────────
    # Avoid warning purely because a minimal project has no .env files.
    if (
        project_type == ProjectType.UNCLEAR
        and not template_path
        and not existing_env_files
    ):
        results.append(
            CheckResult(
                name="Environment Configuration",
                category="environment",
                status=CheckStatus.NOT_CHECKED,
                message=(
                    "No environment configuration files found (.env, .env.example, etc.). "
                    "Project type is unclear; cannot determine whether environment "
                    "variables are required without additional context."
                ),
            )
        )
        return results

    # ── Backward-compatible / WEB_SERVICE_OR_APP / CLI-with-template path ───

    # Case 1: Neither template nor any env files found
    if not template_path and not existing_env_files:
        results.append(
            CheckResult(
                name="Environment Configuration",
                category="environment",
                status=CheckStatus.WARNING,
                message="No .env or .env.example files detected in the project root.",
                fix=(
                    "Create a .env.example documenting expected environment variable names "
                    "if the app requires configuration."
                ),
            )
        )
        return results

    # Case 2: Template exists but no env file exists
    if template_path and not existing_env_files:
        template_keys = sorted(extract_variable_names(template_path))
        results.append(
            CheckResult(
                name="Environment File Presence",
                category="environment",
                status=CheckStatus.FAIL,
                message=f"Found {template_path.name} with {len(template_keys)} expected variables, but no .env file exists.",
                fix=f"Create a .env file from {template_path.name} and configure appropriate local values.",
                source_location={"template_file": template_path.name},
                details={
                    "template_file": template_path.name,
                    "expected_variable_names": template_keys,
                },
            )
        )
        return results

    # Aggregate variable names across all existing environment files
    env_file_names = [f.name for f in existing_env_files]
    target_env_label = " + ".join(env_file_names)
    all_env_keys_set: Set[str] = set()
    for ef in existing_env_files:
        all_env_keys_set.update(extract_variable_names(ef))

    # Case 3: Env file(s) exist but no template exists
    if existing_env_files and not template_path:
        env_keys = sorted(all_env_keys_set)
        results.append(
            CheckResult(
                name="Environment Template Parity",
                category="environment",
                status=CheckStatus.WARNING,
                message=(
                    f"Found {target_env_label} with {len(env_keys)} variable(s) defined, "
                    f"but no example template was found."
                ),
                fix="Create a .env.example documenting variable names (without secret values) for reproducible setups.",
                # Env files were confirmed present and read; values are filenames only.
                source_location={"env_files": ", ".join(env_file_names)},
                details={
                    "inspected_files": env_file_names,
                    "configured_variable_names": env_keys,
                },
            )
        )
        return results

    # Case 4: Both template and env file(s) exist → compare names
    assert template_path is not None

    template_keys_set = extract_variable_names(template_path)

    missing_keys = sorted(template_keys_set - all_env_keys_set)
    extra_keys = sorted(all_env_keys_set - template_keys_set)
    matched_keys = sorted(template_keys_set & all_env_keys_set)

    primary_target = ".env.local" if ".env.local" in env_file_names else env_file_names[0]

    if missing_keys:
        missing_list_str = ", ".join(missing_keys)
        results.append(
            CheckResult(
                name="Environment Variable Parity",
                category="environment",
                status=CheckStatus.WARNING,
                message=(
                    f"Missing {len(missing_keys)} variable(s) in {target_env_label} "
                    f"that are specified in {template_path.name}."
                ),
                fix=(
                    f"Add missing variables to {primary_target}: {missing_list_str} "
                    f"(do not commit secret values)."
                ),
                # Both template and env files inspected; values are filenames only.
                source_location={
                    "template_file": template_path.name,
                    "env_files": ", ".join(env_file_names),
                },
                details={
                    "inspected_files": env_file_names,
                    "missing_variable_names": missing_keys,
                    "matched_variable_names": matched_keys,
                    "extra_variable_names": extra_keys,
                },
            )
        )
    else:
        results.append(
            CheckResult(
                name="Environment Variable Parity",
                category="environment",
                status=CheckStatus.PASS,
                message=(
                    f"All {len(template_keys_set)} variable(s) defined in "
                    f"{template_path.name} are present in {target_env_label}."
                ),
                # Both template and env files inspected; values are filenames only.
                source_location={
                    "template_file": template_path.name,
                    "env_files": ", ".join(env_file_names),
                },
                details={
                    "inspected_files": env_file_names,
                    "configured_variable_names": matched_keys,
                    "extra_variable_names": extra_keys,
                },
            )
        )

    return results
