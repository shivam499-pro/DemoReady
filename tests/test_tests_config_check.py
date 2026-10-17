"""Unit tests for test script configuration and opt-in execution."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from demoready.checks.tests_config import (
    check_test_script_configuration,
    execute_test_command,
    run_tests_checks,
)
from demoready.core.models import CheckStatus


class TestTestsConfigCheck(unittest.TestCase):
    def test_missing_scripts_or_test_key(self):
        pkg_no_scripts = {"name": "sample"}
        res1 = check_test_script_configuration(pkg_no_scripts)
        self.assertEqual(res1.status, CheckStatus.WARNING)
        self.assertIn("No 'test' script defined", res1.message)

        pkg_empty_scripts = {"name": "sample", "scripts": {}}
        res2 = check_test_script_configuration(pkg_empty_scripts)
        self.assertEqual(res2.status, CheckStatus.WARNING)

    def test_placeholder_default_npm_test(self):
        pkg_placeholder = {
            "name": "sample",
            "scripts": {
                "test": 'echo "Error: no test specified" && exit 1',
            },
        }
        res = check_test_script_configuration(pkg_placeholder)
        self.assertEqual(res.status, CheckStatus.FAIL)
        self.assertIn("Placeholder test script detected", res.message)
        self.assertIsNotNone(res.fix)

    def test_exact_dummy_scripts(self):
        for dummy in ["exit 1", "exit 0", "false", "true"]:
            pkg = {"name": "sample", "scripts": {"test": dummy}}
            res = check_test_script_configuration(pkg)
            self.assertEqual(res.status, CheckStatus.FAIL, f"Failed to flag dummy script: {dummy}")
            self.assertIn("Placeholder test script detected", res.message)

    def test_valid_test_command(self):
        pkg_valid = {
            "name": "sample",
            "scripts": {
                "test": "vitest run --passWithNoTests",
            },
        }
        res = check_test_script_configuration(pkg_valid)
        self.assertEqual(res.status, CheckStatus.PASS)
        self.assertIn("Configured test command", res.message)

    def test_default_not_checked_execution(self):
        pkg_valid = {
            "name": "sample",
            "scripts": {"test": "vitest run"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_tests_checks(Path(tmpdir), pkg_data=pkg_valid, run_tests=False)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            # Default execution is NOT_CHECKED
            self.assertEqual(results[1].status, CheckStatus.NOT_CHECKED)
            self.assertEqual(results[1].name, "Test Command Execution")
            self.assertIn("skipped by default", results[1].message)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_opt_in_execution_success(self, mock_which, mock_run):
        mock_which.return_value = "npm"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npm", "test"],
            returncode=0,
            stdout="All tests passed",
            stderr="",
        )

        pkg_valid = {"scripts": {"test": "node --test"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_tests_checks(Path(tmpdir), pkg_data=pkg_valid, run_tests=True, test_timeout=15)
            self.assertEqual(len(results), 2)
            exec_check = results[1]
            self.assertEqual(exec_check.status, CheckStatus.PASS)
            self.assertIn("executed successfully", exec_check.message)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_opt_in_execution_failure(self, mock_which, mock_run):
        mock_which.return_value = "npm"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npm", "test"],
            returncode=1,
            stdout="",
            stderr="1 test failed",
        )

        pkg_valid = {"scripts": {"test": "jest"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_tests_checks(Path(tmpdir), pkg_data=pkg_valid, run_tests=True, test_timeout=15)
            self.assertEqual(len(results), 2)
            exec_check = results[1]
            self.assertEqual(exec_check.status, CheckStatus.FAIL)
            self.assertIn("failed with exit code 1", exec_check.message)
            self.assertIsNotNone(exec_check.fix)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_opt_in_execution_timeout(self, mock_which, mock_run):
        mock_which.return_value = "npm"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["npm", "test"], timeout=10)

        pkg_valid = {"scripts": {"test": "sleep 100"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_tests_checks(Path(tmpdir), pkg_data=pkg_valid, run_tests=True, test_timeout=10)
            self.assertEqual(len(results), 2)
            exec_check = results[1]
            self.assertEqual(exec_check.status, CheckStatus.FAIL)
            self.assertIn("timed out after 10 seconds", exec_check.message)
            self.assertIn("--test-timeout", exec_check.fix)


if __name__ == "__main__":
    unittest.main()
