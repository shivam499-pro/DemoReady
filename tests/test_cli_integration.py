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


if __name__ == "__main__":
    unittest.main()
