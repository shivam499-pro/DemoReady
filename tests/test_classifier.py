"""Unit tests for the project type classifier and NOT_APPLICABLE integration."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from demoready.checks.endpoints import run_endpoints_checks
from demoready.checks.environment import run_environment_checks
from demoready.core.classifier import (
    ClassificationResult,
    ProjectType,
    classify_project,
)
from demoready.core.models import CheckResult, CheckStatus, InspectionReport
from demoready.core.runner import run_inspection
from demoready.formatters.console import format_console_report
from demoready.formatters.json_formatter import format_json_report


class TestClassifier(unittest.TestCase):
    def test_missing_or_empty_pkg_data_is_unclear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res = classify_project(Path(tmpdir), None)
            self.assertEqual(res.project_type, ProjectType.UNCLEAR)
            self.assertTrue(len(res.evidence) > 0)

    def test_monorepo_via_workspaces_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-monorepo",
                "workspaces": ["packages/*"],
            }
            res = classify_project(Path(tmpdir), pkg)
            self.assertEqual(res.project_type, ProjectType.MONOREPO_ROOT)
            self.assertTrue(any("workspaces" in e for e in res.evidence))

    def test_monorepo_via_config_file(self):
        for cfg_file in ["pnpm-workspace.yaml", "lerna.json", "turbo.json", "nx.json"]:
            with tempfile.TemporaryDirectory() as tmpdir:
                td = Path(tmpdir)
                (td / cfg_file).write_text("{}", encoding="utf-8")
                pkg = {"name": "repo-with-cfg"}
                res = classify_project(td, pkg)
                self.assertEqual(res.project_type, ProjectType.MONOREPO_ROOT)
                self.assertTrue(any(cfg_file in e for e in res.evidence))

    def test_cli_tool_classification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            pkg = {
                "name": "my-cli",
                "bin": {"my-cli": "./bin/cli.js"},
                "dependencies": {"commander": "^11.0.0"},
            }
            res = classify_project(td, pkg)
            self.assertEqual(res.project_type, ProjectType.CLI_TOOL)
            self.assertTrue(any("bin" in e for e in res.evidence))

    def test_cli_tool_with_deployment_file_not_pure_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "Dockerfile").write_text("FROM node:18\n", encoding="utf-8")
            pkg = {
                "name": "app-with-cli-helper",
                "bin": "./bin/run.js",
                "scripts": {"start": "node server.js"},
            }
            res = classify_project(td, pkg)
            # Has bin, but also has Dockerfile + start script -> WEB_SERVICE_OR_APP (>=2 app signals)
            self.assertEqual(res.project_type, ProjectType.WEB_SERVICE_OR_APP)

    def test_reusable_library_classification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            pkg = {
                "name": "my-lodash-utils",
                "version": "1.0.0",
                "main": "dist/index.js",
                "module": "dist/index.mjs",
                "types": "dist/index.d.ts",
                "exports": {".": "./dist/index.js"},
                "scripts": {
                    "build": "tsc",
                    "prepublishOnly": "npm run build",
                },
            }
            res = classify_project(td, pkg)
            self.assertEqual(res.project_type, ProjectType.REUSABLE_LIBRARY)
            self.assertTrue(any("Library publish fields" in e for e in res.evidence))

    def test_library_not_classified_if_private_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            pkg = {
                "name": "internal-package",
                "private": True,
                "types": "dist/index.d.ts",
            }
            res = classify_project(td, pkg)
            # Not classified as library because private: true
            self.assertNotEqual(res.project_type, ProjectType.REUSABLE_LIBRARY)

    def test_web_service_requires_at_least_two_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # Single signal: only express in dependencies -> UNCLEAR
            res1 = classify_project(td, {"name": "test1", "dependencies": {"express": "^4.18.0"}})
            self.assertEqual(res1.project_type, ProjectType.UNCLEAR)

            # Single signal: only "private": true -> UNCLEAR
            res2 = classify_project(td, {"name": "test2", "private": True})
            self.assertEqual(res2.project_type, ProjectType.UNCLEAR)

            # Single signal: only Dockerfile -> UNCLEAR
            (td / "Dockerfile").write_text("FROM node:18\n", encoding="utf-8")
            res3 = classify_project(td, {"name": "test3"})
            self.assertEqual(res3.project_type, ProjectType.UNCLEAR)

            # Two signals: Dockerfile + start script -> WEB_SERVICE_OR_APP
            res4 = classify_project(td, {"name": "test4", "scripts": {"start": "node server.js"}})
            self.assertEqual(res4.project_type, ProjectType.WEB_SERVICE_OR_APP)

            # Two signals: express dependency + "private": true -> WEB_SERVICE_OR_APP
            (td / "Dockerfile").unlink()
            res5 = classify_project(
                td,
                {
                    "name": "test5",
                    "private": True,
                    "dependencies": {"express": "^4.18.0"},
                },
            )
            self.assertEqual(res5.project_type, ProjectType.WEB_SERVICE_OR_APP)


class TestApplicabilityIntegration(unittest.TestCase):
    def test_library_environment_and_endpoints_are_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            env_results = run_environment_checks(td, project_type=ProjectType.REUSABLE_LIBRARY)
            self.assertEqual(len(env_results), 1)
            self.assertEqual(env_results[0].status, CheckStatus.NOT_APPLICABLE)
            self.assertIn("not applicable to reusable library", env_results[0].message)

            endpoint_results = run_endpoints_checks(td, project_type=ProjectType.REUSABLE_LIBRARY)
            self.assertEqual(len(endpoint_results), 2)
            self.assertEqual(endpoint_results[0].status, CheckStatus.NOT_APPLICABLE)
            self.assertEqual(endpoint_results[1].status, CheckStatus.NOT_APPLICABLE)

    def test_cli_environment_not_applicable_unless_template_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # No template -> NOT_APPLICABLE
            res_no_template = run_environment_checks(td, project_type=ProjectType.CLI_TOOL)
            self.assertEqual(len(res_no_template), 1)
            self.assertEqual(res_no_template[0].status, CheckStatus.NOT_APPLICABLE)

            # With template -> normal checks (e.g. FAIL when template exists but no env)
            (td / ".env.example").write_text("CLI_TOKEN=\n", encoding="utf-8")
            res_with_template = run_environment_checks(td, project_type=ProjectType.CLI_TOOL)
            self.assertEqual(len(res_with_template), 1)
            self.assertEqual(res_with_template[0].status, CheckStatus.FAIL)

    def test_full_inspection_on_library_project_is_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "math-lib",
                    "version": "1.0.0",
                    "types": "dist/index.d.ts",
                    "main": "dist/index.js",
                    "scripts": {
                        "build": "tsc",
                        "test": "vitest run",
                        "prepublishOnly": "npm run build",
                    },
                }),
                encoding="utf-8",
            )
            (td / "package-lock.json").write_text("{}", encoding="utf-8")
            (td / "node_modules").mkdir()

            report = run_inspection(td)
            self.assertEqual(report.project_type, "REUSABLE_LIBRARY")
            self.assertEqual(report.readiness_status, "READY")
            self.assertGreater(report.summary[CheckStatus.NOT_APPLICABLE.value], 0)

            # Check JSON serialization includes project_type and NOT_APPLICABLE count
            json_str = format_json_report(report)
            data = json.loads(json_str)
            self.assertEqual(data["project_type"], "REUSABLE_LIBRARY")
            self.assertIn("NOT_APPLICABLE", data["summary"])

            # Check console formatter output
            console_str = format_console_report(report)
            self.assertIn("NOT_APPLICABLE", console_str)
            self.assertIn("[READY FOR DEMO]", console_str)

    def test_realistic_sample_app_classification_and_inspection(self):
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "realistic_sample_app"
        if not fixture_path.exists():
            self.skipTest("realistic_sample_app fixture directory not found")

        # 1. Fresh-clone behavior on the checked-in fixture directly:
        # Without .env or node_modules checked into Git, pre-flight inspection
        # detects missing dependencies (WARNING) and missing .env (FAIL).
        report_fresh = run_inspection(fixture_path)
        self.assertEqual(report_fresh.project_type, "WEB_SERVICE_OR_APP")
        self.assertEqual(report_fresh.readiness_status, "NOT_READY")
        self.assertEqual(report_fresh.summary[CheckStatus.FAIL.value], 1)
        self.assertEqual(report_fresh.summary[CheckStatus.WARNING.value], 1)

        # Static health endpoint is detected statically even before local setup
        health_checks = [c for c in report_fresh.results if c.name == "Static Health Endpoint Definition"]
        self.assertEqual(len(health_checks), 1)
        self.assertEqual(health_checks[0].status, CheckStatus.PASS)

        # 2. Configured-ready behavior in an isolated temporary copy:
        # Simulate developer setup (creating .env from template and installing dependencies)
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            shutil.copytree(fixture_path, td, dirs_exist_ok=True)
            # Create matching .env from .env.example
            example_content = (fixture_path / ".env.example").read_text(encoding="utf-8")
            (td / ".env").write_text(example_content, encoding="utf-8")
            # Create node_modules directory
            (td / "node_modules").mkdir()

            report_ready = run_inspection(td)
            self.assertEqual(report_ready.project_type, "WEB_SERVICE_OR_APP")
            self.assertEqual(report_ready.readiness_status, "READY")
            self.assertEqual(report_ready.summary[CheckStatus.FAIL.value], 0)
            self.assertEqual(report_ready.summary[CheckStatus.WARNING.value], 0)

            env_checks = [c for c in report_ready.results if c.category == "environment"]
            self.assertTrue(any(c.status == CheckStatus.PASS for c in env_checks))


if __name__ == "__main__":
    unittest.main()
