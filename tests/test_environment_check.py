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

    def test_unusual_env_formatting_and_prefixing(self):
        """Verify quotes, export syntax, blank values, and comment styles (//, ;) are parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            env_content = (
                "# Full-line hash comment\n"
                "// Double-slash comment\n"
                "; Semicolon comment\n"
                "   # Leading whitespace comment\n"
                'export "QUOTED_VAR"="secret_val"\n'
                "'SINGLE_QUOTED_VAR'=12345\n"
                "BLANK_VAR=\n"
                "SPACED_KEY = value\n"
                "INLINE_COMMENT_VAR=value # trailing comment\n"
                "=MALFORMED_NO_KEY\n"
            )
            env_file = td / ".env"
            env_file.write_text(env_content, encoding="utf-8")

            names = extract_variable_names(env_file)
            self.assertIn("QUOTED_VAR", names)
            self.assertIn("SINGLE_QUOTED_VAR", names)
            self.assertIn("BLANK_VAR", names)
            self.assertIn("INLINE_COMMENT_VAR", names)
            self.assertNotIn("MALFORMED_NO_KEY", names)
            self.assertNotIn("secret_val", names)

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

    def test_variable_split_between_env_and_env_local_no_false_warning(self):
        """1. Variable split between .env and .env.local produces no false missing variable warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nDATABASE_URL=\nAPI_KEY=\n", encoding="utf-8")
            (td / ".env").write_text("PORT=3000\n", encoding="utf-8")
            (td / ".env.local").write_text("DATABASE_URL=postgres://localhost:5432\nAPI_KEY=local_key\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertIn("All 3 variable(s)", results[0].message)
            self.assertEqual(results[0].details["inspected_files"], [".env", ".env.local"])
            self.assertEqual(
                results[0].details["configured_variable_names"],
                ["API_KEY", "DATABASE_URL", "PORT"],
            )

    def test_variable_present_in_both_files_counted_once(self):
        """2. A variable present in both files is counted only once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nSHARED_CONFIG=\n", encoding="utf-8")
            (td / ".env").write_text("PORT=3000\nSHARED_CONFIG=default\n", encoding="utf-8")
            (td / ".env.local").write_text("PORT=8080\nSHARED_CONFIG=override\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            # Counted only once: 2 variables configured
            self.assertEqual(
                results[0].details["configured_variable_names"],
                ["PORT", "SHARED_CONFIG"],
            )

    def test_only_env_exists(self):
        """3. Only .env exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nDATABASE_URL=\n", encoding="utf-8")
            (td / ".env").write_text("PORT=3000\nDATABASE_URL=postgres://localhost:5432\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertEqual(results[0].details["inspected_files"], [".env"])
            self.assertEqual(results[0].details["configured_variable_names"], ["DATABASE_URL", "PORT"])

    def test_only_env_local_exists(self):
        """4. Only .env.local exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nAPI_KEY=\n", encoding="utf-8")
            (td / ".env.local").write_text("PORT=3000\nAPI_KEY=local_val\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertEqual(results[0].details["inspected_files"], [".env.local"])
            self.assertEqual(results[0].details["configured_variable_names"], ["API_KEY", "PORT"])

    def test_neither_file_exists(self):
        """5. Neither .env nor .env.local exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("PORT=3000\nAPI_KEY=\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.FAIL)
            self.assertIn("no .env file exists", results[0].message)

    def test_secret_value_from_either_file_never_leaks(self):
        """6. Secret value from either file never appears in console or JSON output."""
        env_secret = "SECRET_IN_ENV_FILE_11111"
        env_local_secret = "SECRET_IN_ENV_LOCAL_FILE_22222"

        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("SECRET_A=\nSECRET_B=\nMISSING_C=\n", encoding="utf-8")
            (td / ".env").write_text(f"SECRET_A={env_secret}\n", encoding="utf-8")
            (td / ".env.local").write_text(f"SECRET_B={env_local_secret}\n", encoding="utf-8")

            results = run_environment_checks(td)
            report = InspectionReport(target_path=str(td), results=results)

            console_output = format_console_report(report)
            json_output = format_json_report(report)
            report_dict = report.to_dict()
            dict_str = json.dumps(report_dict)

            # Neither secret should appear in console, JSON, or dict
            for secret in [env_secret, env_local_secret]:
                self.assertNotIn(secret, console_output, f"Secret leaked in console: {secret}")
                self.assertNotIn(secret, json_output, f"Secret leaked in JSON: {secret}")
                self.assertNotIn(secret, dict_str, f"Secret leaked in dict: {secret}")

            for r in results:
                self.assertNotIn(env_secret, r.message)
                self.assertNotIn(env_local_secret, r.message)
                if r.fix:
                    self.assertNotIn(env_secret, r.fix)
                    self.assertNotIn(env_local_secret, r.fix)

    def test_source_location_env_filenames_only_never_values(self):
        """Regression 5: env parity results carry source_location containing
        only filenames.  Secret values from .env / .env.local must never appear
        in source_location, console output, or JSON output."""
        env_secret = "ENV_SECRET_VALUE_AAAAA"
        local_secret = "LOCAL_SECRET_VALUE_BBBBB"

        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / ".env.example").write_text("SECRET_A=\nSECRET_B=\n", encoding="utf-8")
            (td / ".env").write_text(f"SECRET_A={env_secret}\n", encoding="utf-8")
            (td / ".env.local").write_text(f"SECRET_B={local_secret}\n", encoding="utf-8")

            results = run_environment_checks(td)
            self.assertEqual(len(results), 1)
            result = results[0]

            # source_location must be present and contain filenames only
            self.assertIsNotNone(result.source_location)
            sl_str = json.dumps(result.source_location)
            self.assertIn(".env.example", sl_str)
            self.assertNotIn(env_secret, sl_str, "env secret leaked into source_location")
            self.assertNotIn(local_secret, sl_str, "env.local secret leaked into source_location")

            # Verify secrets absent from full report outputs
            report = InspectionReport(target_path=str(td), results=results)
            console_out = format_console_report(report)
            json_out = format_json_report(report)
            for secret in [env_secret, local_secret]:
                self.assertNotIn(secret, console_out, f"Secret in console: {secret}")
                self.assertNotIn(secret, json_out, f"Secret in JSON: {secret}")


if __name__ == "__main__":
    unittest.main()

