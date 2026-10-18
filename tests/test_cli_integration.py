"""End-to-end integration tests for DemoReady CLI."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from demoready.cli import main


class TestCliIntegration(unittest.TestCase):
    def test_cli_on_missing_directory(self):
        nonexistent = Path(tempfile.gettempdir()) / "nonexistent_dir_9999"
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = main(["--path", str(nonexistent)])
            self.assertEqual(exit_code, 1)
            output = mock_stdout.getvalue()
            self.assertIn("FAIL", output)
            self.assertIn("does not exist", output)

    def test_cli_on_ready_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "sample-demo-app",
                    "version": "1.0.0",
                    "scripts": {"test": "vitest run"},
                }),
                encoding="utf-8",
            )
            (td / "package-lock.json").write_text("{}", encoding="utf-8")
            (td / "node_modules").mkdir()
            (td / ".env.example").write_text("PORT=3000\n", encoding="utf-8")
            (td / ".env").write_text("PORT=3000\n", encoding="utf-8")
            src_dir = td / "src"
            src_dir.mkdir()
            (src_dir / "index.ts").write_text('app.get("/health", (req, res) => res.send("OK"));', encoding="utf-8")

            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = main(["--path", str(td)])
                self.assertEqual(exit_code, 0)
                output = mock_stdout.getvalue()
                self.assertIn("[READY FOR DEMO]", output)
                self.assertIn("Static Health Endpoint Definition", output)

    def test_cli_json_output_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "json-test-app",
                    "version": "0.1.0",
                    "scripts": {"test": "echo 'not configured' && exit 1"},
                }),
                encoding="utf-8",
            )

            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = main(["--path", str(td), "--json"])
                # Since placeholder test script is a FAIL, exit code should be 1
                self.assertEqual(exit_code, 1)
                raw_json = mock_stdout.getvalue().strip()
                parsed = json.loads(raw_json)

                self.assertIn("target_path", parsed)
                self.assertIn("readiness_status", parsed)
                self.assertIn("summary", parsed)
                self.assertIn("checks", parsed)
                self.assertEqual(parsed["readiness_status"], "NOT_READY")
                self.assertGreater(parsed["summary"]["FAIL"], 0)

    def test_cli_version_flag(self):
        with self.assertRaises(SystemExit) as cm:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_cli_invalid_timeout_rejected_without_traceback(self):
        """Verify invalid timeout argument values are rejected with error and no traceback."""
        for invalid_val in ["0", "-5"]:
            with self.assertRaises(SystemExit) as cm:
                with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                    main(["--test-timeout", invalid_val])
            # argparse exits with code 2 on argument error
            self.assertEqual(cm.exception.code, 2)
            err_output = mock_stderr.getvalue()
            self.assertIn("error: --test-timeout must be a positive integer", err_output)
            self.assertNotIn("Traceback", err_output)

    def test_output_flag_writes_valid_json_file(self):
        """Verify --output flag creates a valid JSON file with inspection results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "sample-output-app",
                    "version": "1.0.0",
                    "scripts": {"test": "vitest run"},
                }),
                encoding="utf-8",
            )
            out_file = td / "report.json"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--output", str(out_file)])
                self.assertEqual(exit_code, 0)
                self.assertTrue(out_file.exists())
                content = out_file.read_text(encoding="utf-8")
                parsed = json.loads(content)
                self.assertIn("target_path", parsed)
                self.assertIn("summary", parsed)
                self.assertIn("checks", parsed)

    def test_output_flag_content_matches_json_stdout(self):
        """Verify the JSON written to --output exactly matches --json stdout output for the same scan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "match-test-app",
                    "version": "1.0.0",
                    "scripts": {"test": "jest"},
                }),
                encoding="utf-8",
            )
            out_file = td / "report.json"

            from demoready.core.runner import run_inspection
            fixed_report = run_inspection(target_path=td)

            with patch("demoready.cli.run_inspection", return_value=fixed_report):
                # Run with --json to capture stdout
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    main(["--path", str(td), "--json"])
                    expected_stdout = mock_stdout.getvalue()

                # Run with --output
                with patch("sys.stdout", new_callable=io.StringIO), \
                     patch("sys.stderr", new_callable=io.StringIO):
                    main(["--path", str(td), "--output", str(out_file)])

            file_content = out_file.read_text(encoding="utf-8")
            self.assertEqual(file_content, expected_stdout)

    def test_output_flag_stdout_empty_stderr_has_confirmation(self):
        """Verify stdout is empty and stderr contains the success confirmation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({
                    "name": "quiet-app",
                    "version": "1.0.0",
                    "scripts": {"test": "vitest run"},
                }),
                encoding="utf-8",
            )
            out_file = td / "out.json"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--output", str(out_file)])
                self.assertEqual(exit_code, 0)
                self.assertEqual(mock_stdout.getvalue(), "")
                stderr_output = mock_stderr.getvalue()
                self.assertIn(f"Report written to: {out_file}", stderr_output)

    def test_output_flag_nonexistent_parent_dir_clean_error(self):
        """Verify missing parent directory results in exit 2 and clean error without traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({"name": "test-app", "version": "1.0.0"}),
                encoding="utf-8",
            )
            invalid_out = td / "nonexistent_subdir" / "report.json"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--output", str(invalid_out)])
                self.assertEqual(exit_code, 2)
                self.assertEqual(mock_stdout.getvalue(), "")
                err_output = mock_stderr.getvalue()
                self.assertIn("error: output directory does not exist", err_output)
                self.assertNotIn("Traceback", err_output)

    def test_output_flag_target_is_existing_directory(self):
        """Verify specifying an existing directory as --output exits with 2 and clean error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({"name": "test-app", "version": "1.0.0"}),
                encoding="utf-8",
            )
            dir_target = td / "some_dir"
            dir_target.mkdir()
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--output", str(dir_target)])
                self.assertEqual(exit_code, 2)
                self.assertEqual(mock_stdout.getvalue(), "")
                err_output = mock_stderr.getvalue()
                self.assertIn("error: --output path is a directory", err_output)
                self.assertNotIn("Traceback", err_output)

    def test_output_flag_failed_project_preserves_readiness_exit_code(self):
        """Verify that a failing project still returns exit code 1 when --output succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # Placeholder test script triggers FAIL
            (td / "package.json").write_text(
                json.dumps({
                    "name": "failing-app",
                    "version": "1.0.0",
                    "scripts": {"test": "echo 'not configured' && exit 1"},
                }),
                encoding="utf-8",
            )
            out_file = td / "report.json"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--output", str(out_file)])
                self.assertEqual(exit_code, 1)
                self.assertEqual(mock_stdout.getvalue(), "")
                self.assertIn(f"Report written to: {out_file}", mock_stderr.getvalue())
                self.assertTrue(out_file.exists())
                parsed = json.loads(out_file.read_text(encoding="utf-8"))
                self.assertEqual(parsed["readiness_status"], "NOT_READY")

    def test_output_flag_combined_with_json_flag(self):
        """Verify passing both --json and --output behaves identically to --output alone."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(
                json.dumps({"name": "combo-app", "version": "1.0.0"}),
                encoding="utf-8",
            )
            out_file = td / "report.json"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                 patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                exit_code = main(["--path", str(td), "--json", "--output", str(out_file)])
                self.assertEqual(mock_stdout.getvalue(), "")
                self.assertIn(f"Report written to: {out_file}", mock_stderr.getvalue())
                self.assertTrue(out_file.exists())


if __name__ == "__main__":
    unittest.main()


