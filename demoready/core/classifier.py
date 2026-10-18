"""
Evidence-based project type classifier for Node.js repositories.

Rules are applied in a strict priority order.  No single signal is sufficient
to classify a project as a WEB_SERVICE_OR_APP; at least two independent signals
are required.  This prevents false positives for reusable packages that happen
to list a web framework as a development dependency.

Signals intentionally excluded:
  - "main" field: used by both apps (entry point) and libraries (package root).
  - "private": true alone: insufficient without deployment or server evidence.
  - A single web-framework dependency: frameworks can be library peer-deps too.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectType(str, Enum):
    WEB_SERVICE_OR_APP = "WEB_SERVICE_OR_APP"
    REUSABLE_LIBRARY   = "REUSABLE_LIBRARY"
    CLI_TOOL           = "CLI_TOOL"
    MONOREPO_ROOT      = "MONOREPO_ROOT"
    UNCLEAR            = "UNCLEAR"


@dataclass
class ClassificationResult:
    """Immutable record of the classifier's decision and its supporting evidence."""
    project_type: ProjectType
    evidence: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Signal catalogs
# ---------------------------------------------------------------------------

_MONOREPO_CONFIG_FILES = frozenset({
    "pnpm-workspace.yaml",
    "lerna.json",
    "turbo.json",
    "nx.json",
    "rush.json",
})

# Deployment / hosting platform configuration files.
_DEPLOYMENT_FILES = frozenset({
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Procfile",
    "fly.toml",
    "render.yaml",
    "vercel.json",
    "heroku.yml",
    "railway.toml",
    "app.yaml",     # Google App Engine
    ".platform",
})

# Scripts that start a persistent server daemon (not one-off commands).
_SERVER_SCRIPT_KEYS = frozenset({"start", "serve"})

# Production web / API server frameworks.  Only matches when found in
# "dependencies" (not devDependencies) to reduce false positives.
_WEB_FRAMEWORK_DEPS = frozenset({
    "express", "fastify", "koa", "@hapi/hapi", "hapi",
    "next", "nuxt", "@nuxt/core", "sveltekit", "@sveltejs/kit",
    "@nestjs/core", "polka", "restify", "sails",
    "@feathersjs/feathers", "feathers",
})

# CLI toolkit libraries.
_CLI_FRAMEWORK_DEPS = frozenset({
    "commander", "yargs", "cac", "meow", "oclif", "minimist",
    "inquirer", "prompts", "clipanion", "caporal",
})

# Fields that indicate a package is intended for npm publication as a library.
# "main" is intentionally excluded: apps also use it as the server entry point.
_LIBRARY_PUBLISH_FIELDS = frozenset({
    "module", "exports", "types", "typings", "files", "publishConfig",
})

# Lifecycle hooks that only make sense when publishing to a registry.
_LIBRARY_PUBLISH_SCRIPT_KEYS = frozenset({
    "prepublishOnly", "prepare", "prepack",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_project(
    target_path: Path,
    pkg_data: Optional[Dict[str, Any]],
) -> ClassificationResult:
    """
    Classify a Node.js project using multiple independent signals.

    Classification priority (first match wins):
    1. MONOREPO_ROOT  – any workspace config or "workspaces" field.
    2. CLI_TOOL       – "bin" entry present, no deployment files.
    3. REUSABLE_LIBRARY – publish-oriented fields, not private, no daemon
                          start script, no deployment files, no "bin".
    4. WEB_SERVICE_OR_APP – at least two independent deployment/server signals.
    5. UNCLEAR        – insufficient or conflicting evidence.
    """
    if not pkg_data:
        return ClassificationResult(
            project_type=ProjectType.UNCLEAR,
            evidence=["package.json is missing or unparseable; classification not possible"],
        )

    # Extract commonly-used fields once.
    scripts: Dict[str, str] = (
        pkg_data.get("scripts", {})
        if isinstance(pkg_data.get("scripts"), dict)
        else {}
    )
    prod_deps: Dict[str, str] = (
        pkg_data.get("dependencies", {})
        if isinstance(pkg_data.get("dependencies"), dict)
        else {}
    )
    dev_deps: Dict[str, str] = (
        pkg_data.get("devDependencies", {})
        if isinstance(pkg_data.get("devDependencies"), dict)
        else {}
    )
    all_deps = {**prod_deps, **dev_deps}
    is_private: bool = pkg_data.get("private") is True
    bin_defined: bool = "bin" in pkg_data

    # ------------------------------------------------------------------
    # 1. MONOREPO_ROOT
    # ------------------------------------------------------------------
    monorepo_evidence: List[str] = []
    if "workspaces" in pkg_data:
        monorepo_evidence.append('"workspaces" field present in package.json')
    for cfg in sorted(_MONOREPO_CONFIG_FILES):
        if (target_path / cfg).exists():
            monorepo_evidence.append(f'"{cfg}" found at project root')
    if monorepo_evidence:
        return ClassificationResult(ProjectType.MONOREPO_ROOT, monorepo_evidence)

    # Compute deployment-file hits once; used by both CLI and Library rules.
    deploy_hits = sorted(f for f in _DEPLOYMENT_FILES if (target_path / f).exists())

    # ------------------------------------------------------------------
    # 2. CLI_TOOL
    # ------------------------------------------------------------------
    cli_evidence: List[str] = []
    if bin_defined:
        cli_evidence.append('"bin" entry found in package.json')
    cli_dep_hits = sorted(d for d in _CLI_FRAMEWORK_DEPS if d in all_deps)
    if cli_dep_hits:
        cli_evidence.append(f'CLI framework dependencies: {", ".join(cli_dep_hits)}')

    # If "bin" is present alongside deployment files the project is likely an
    # app that exposes a CLI helper — not a standalone CLI tool.
    if bin_defined and not deploy_hits:
        return ClassificationResult(ProjectType.CLI_TOOL, cli_evidence)

    # ------------------------------------------------------------------
    # 3. REUSABLE_LIBRARY
    # ------------------------------------------------------------------
    lib_fields_found = sorted(f for f in _LIBRARY_PUBLISH_FIELDS if f in pkg_data)
    lib_scripts_found = sorted(s for s in _LIBRARY_PUBLISH_SCRIPT_KEYS if s in scripts)

    lib_evidence: List[str] = []
    if lib_fields_found:
        lib_evidence.append(
            f'Library publish fields present: {", ".join(lib_fields_found)}'
        )
    if lib_scripts_found:
        lib_evidence.append(
            f'Publish lifecycle scripts defined: {", ".join(lib_scripts_found)}'
        )

    has_daemon_start = any(k in scripts for k in _SERVER_SCRIPT_KEYS)

    # All conditions must hold simultaneously to classify as a library.
    if (
        lib_evidence
        and not is_private          # publishable packages are not private
        and not has_daemon_start    # a library does not start a server
        and not deploy_hits         # a library is not deployed as a service
        and not bin_defined         # "bin" is already handled above
    ):
        return ClassificationResult(ProjectType.REUSABLE_LIBRARY, lib_evidence)

    # ------------------------------------------------------------------
    # 4. WEB_SERVICE_OR_APP  (requires ≥2 independent signals)
    # ------------------------------------------------------------------
    app_evidence: List[str] = []
    if is_private:
        app_evidence.append(
            '"private": true indicates a non-publishable deployment unit'
        )
    if deploy_hits:
        app_evidence.append(
            f'Deployment configuration files found: {", ".join(deploy_hits)}'
        )
    server_script_hits = sorted(k for k in _SERVER_SCRIPT_KEYS if k in scripts)
    if server_script_hits:
        app_evidence.append(
            f'Server lifecycle scripts defined: {", ".join(server_script_hits)}'
        )
    web_dep_hits = sorted(d for d in _WEB_FRAMEWORK_DEPS if d in prod_deps)
    if web_dep_hits:
        app_evidence.append(
            f'Web/server framework in dependencies: {", ".join(web_dep_hits)}'
        )

    if len(app_evidence) >= 2:
        return ClassificationResult(ProjectType.WEB_SERVICE_OR_APP, app_evidence)

    # ------------------------------------------------------------------
    # 5. UNCLEAR
    # ------------------------------------------------------------------
    all_weak_evidence = [*app_evidence, *lib_evidence, *cli_evidence]
    return ClassificationResult(
        project_type=ProjectType.UNCLEAR,
        evidence=(
            all_weak_evidence
            or ["Insufficient signals to classify project type confidently"]
        ),
    )
