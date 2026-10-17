"""Unit tests for environment variable checks and zero-secret leakage."""

import json
from pathlib import Path
import tempfile
import unittest

from demoready.checks.environment import extract_variable_names, run_environment_checks
from demoready.core.models import CheckStatus
from demoready.formatters.console import format_console_report
from demoready.formatters.json_formatter import format_json_report
from demoready.core.models import InspectionReport


class TestEnvironmentCheck(unittest.TestCase):
    def test_no_env_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_environment_checks(Path(tmpdir))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.WARNING)
            self.assertIn("No .env or .env.example files detected", results[0].message)

    def test_template_exists_but_no_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nDATABASE_URL=\nAPI_KEY=", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.FAIL)
            self.assertIn("no .env file exists", results[0].message)
            self.assertIn("PORT", results[0].details["expected_variable_names"])
            self.assertIn("DATABASE_URL", results[0].details["expected_variable_names"])

    def test_env_exists_but_no_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env").write_text("PORT=3000\nNODE_ENV=production\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.WARNING)
            self.assertIn("no example template was found", results[0].message)

    def test_template_and_env_parity_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nAPI_KEY=\n", encoding="utf-8")
            (td / ".env").write_text("PORT=8080\nAPI_KEY=val123\nEXTRA_VAL=extra\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertIn("All 2 variable(s)", results[0].message)

    def test_template_standalone_keys_without_equals(self):
        """Verify templates with keys defined without equals sign are parsed safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT\nDATABASE_URL\n", encoding="utf-8")
            (td / ".env").write_text("PORT=8080\nDATABASE_URL=postgres://localhost:5432\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertEqual(results[0].details["configured_variable_names"], ["DATABASE_URL", "PORT"])

    def test_template_and_env_missing_keys_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nSECRET_KEY=\nDATABASE_URL=\n", encoding="utf-8")
            (td / ".env").write_text("PORT=3000\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.WARNING)
            self.assertIn("Missing 2 variable(s)", results[0].message)
            missing = results[0].details["missing_variable_names"]
            self.assertEqual(sorted(missing), ["DATABASE_URL", "SECRET_KEY"])
            self.assertIn("DATABASE_URL", results[0].fix)
            self.assertIn("SECRET_KEY", results[0].fix)

    def test_zero_secret_leakage(self):
        """
        Verify that secret values placed inside .env or .env.example
        are never exposed in results, details, reports, console output, or JSON output.
        """
        secret_value_1 = "SUPER_SECRET_TOKEN_XYZ_9999"
        secret_value_2 = "MY_ULTRA_SECRET_PASSWORD_123"
        secret_value_3 = "postgres://admin:topsecret1234@localhost:5432/db"

        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text(
                f"API_KEY=example_only\nDB_PASS={secret_value_2}\nDATABASE_URL=\n",
                encoding="utf-8",
            )
            (td / ".env").write_text(
                f"API_KEY={secret_value_1}\nDATABASE_URL={secret_value_3}\n",
                encoding="utf-8",
            )

            # Test parser function directly
            parsed_names = extract_variable_names(td / ".env")
            self.assertEqual(parsed_names, {"API_KEY", "DATABASE_URL"})

            # Run checks
            results = run_environment_checks(td)
            report = InspectionReport(target_path=str(td), results=results)

            # Format console and JSON outputs
            console_out = format_console_report(report)
            json_out = format_json_report(report)
            report_dict = report.to_dict()
            dict_str = json.dumps(report_dict)

            # Verify that none of the secrets appear in any output
            for secret in [secret_value_1, secret_value_2, secret_value_3]:
                self.assertNotIn(secret, console_out, f"Secret leaked in console output: {secret}")
                self.assertNotIn(secret, json_out, f"Secret leaked in JSON output: {secret}")
                self.assertNotIn(secret, dict_str, f"Secret leaked in serialized dict: {secret}")

            for r in results:
                self.assertNotIn(secret_value_1, r.message)
                self.assertNotIn(secret_value_2, r.message)
                self.assertNotIn(secret_value_3, r.message)
                if r.fix:
                    self.assertNotIn(secret_value_1, r.fix)
                    self.assertNotIn(secret_value_2, r.fix)
                    self.assertNotIn(secret_value_3, r.fix)


if __name__ == "__main__":
    unittest.main()
