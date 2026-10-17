"""Environment variable checks with strict zero-secret leakage guarantees."""

from pathlib import Path
import re
from typing import List, Optional, Set, Tuple

from demoready.core.models import CheckResult, CheckStatus


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
VAR_PATTERN = re.compile(r"""^\s*(?:export\s+)?["']?([A-Za-z_][A-Za-z0-9_]*)["']?(?:\s*=|\s*$)""")


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


def run_environment_checks(target_path: Path) -> List[CheckResult]:
    """
    Evaluate environment configuration parity without ever revealing secret values.
    """
    template_path = find_first_existing(target_path, ENV_TEMPLATE_CANDIDATES)
    env_path = find_first_existing(target_path, ENV_FILE_CANDIDATES)

    results: List[CheckResult] = []

    # Case 1: Neither template nor .env found
    if not template_path and not env_path:
        results.append(
            CheckResult(
                name="Environment Configuration",
                category="environment",
                status=CheckStatus.WARNING,
                message="No .env or .env.example files detected in the project root.",
                fix="Create a .env.example documenting expected environment variable names if the app requires configuration.",
            )
        )
        return results

    # Case 2: Template exists but .env is missing
    if template_path and not env_path:
        template_keys = sorted(extract_variable_names(template_path))
        results.append(
            CheckResult(
                name="Environment File Presence",
                category="environment",
                status=CheckStatus.FAIL,
                message=f"Found {template_path.name} with {len(template_keys)} expected variables, but no .env file exists.",
                fix=f"Create a .env file from {template_path.name} and configure appropriate local values.",
                details={
                    "template_file": template_path.name,
                    "expected_variable_names": template_keys,
                },
            )
        )
        return results

    # Case 3: .env exists but no template exists
    if env_path and not template_path:
        env_keys = sorted(extract_variable_names(env_path))
        results.append(
            CheckResult(
                name="Environment Template Parity",
                category="environment",
                status=CheckStatus.WARNING,
                message=f"Found {env_path.name} with {len(env_keys)} variables defined, but no example template was found.",
                fix=f"Create a .env.example documenting variable names (without secret values) for reproducible setups.",
                details={
                    "configured_variable_names": env_keys,
                },
            )
        )
        return results

    # Case 4: Both template and .env exist -> compare names
    assert template_path is not None
    assert env_path is not None

    template_keys_set = extract_variable_names(template_path)
    env_keys_set = extract_variable_names(env_path)

    missing_keys = sorted(template_keys_set - env_keys_set)
    extra_keys = sorted(env_keys_set - template_keys_set)
    matched_keys = sorted(template_keys_set & env_keys_set)

    if missing_keys:
        missing_list_str = ", ".join(missing_keys)
        results.append(
            CheckResult(
                name="Environment Variable Parity",
                category="environment",
                status=CheckStatus.WARNING,
                message=f"Missing {len(missing_keys)} variable(s) in {env_path.name} that are specified in {template_path.name}.",
                fix=f"Add missing variables to {env_path.name}: {missing_list_str} (do not commit secret values).",
                details={
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
                message=f"All {len(template_keys_set)} variable(s) defined in {template_path.name} are present in {env_path.name}.",
                details={
                    "configured_variable_names": matched_keys,
                    "extra_variable_names": extra_keys,
                },
            )
        )

    return results
