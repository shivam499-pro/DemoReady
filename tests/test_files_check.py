"""Unit tests for filesystem and required files checks."""

import json
from pathlib import Path
import tempfile
import unittest

from demoready.checks.files import run_files_checks, validate_target_directory
from demoready.core.models import CheckStatus


class TestFilesCheck(unittest.TestCase):
    def test_nonexistent_directory(self):
        nonexistent = Path(tempfile.gettempdir()) / "nonexistent_demoready_test_dir_12345"
        result = validate_target_directory(nonexistent)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, CheckStatus.FAIL)
        self.assertIn("does not exist", result.message)

    def test_file_instead_of_directory(self):
        with tempfile.NamedTemporaryFile() as tmp:
            result = validate_target_directory(Path(tmp.name))
            self.assertIsNotNone(result)
            self.assertEqual(result.status, CheckStatus.FAIL)
            self.assertIn("is a file", result.message)

    def test_missing_package_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results, pkg_data = run_files_checks(Path(tmpdir))
            self.assertIsNone(pkg_data)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.FAIL)
            self.assertIn("Missing required package.json", results[0].message)
            self.assertIsNotNone(results[0].fix)

    def test_malformed_package_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "package.json"
            pkg_file.write_text('{ "name": "bad-json", broken }', encoding="utf-8")

            results, pkg_data = run_files_checks(Path(tmpdir))
            self.assertIsNone(pkg_data)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, CheckStatus.FAIL)
            self.assertIn("malformed", results[0].message.lower())

    def test_package_json_not_an_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "package.json"
            pkg_file.write_text('["item1", "item2"]', encoding="utf-8")

            results, pkg_data = run_files_checks(Path(tmpdir))
            self.assertIsNone(pkg_data)
            self.assertEqual(results[0].status, CheckStatus.FAIL)
            self.assertIn("must be a JSON object", results[0].message)

    def test_valid_package_missing_lockfile_and_node_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "package.json"
            pkg_file.write_text(json.dumps({"name": "test-pkg", "version": "1.0.0"}), encoding="utf-8")

            results, pkg_data = run_files_checks(Path(tmpdir))
            self.assertIsNotNone(pkg_data)
            self.assertEqual(len(results), 3)

            # Check 1: package.json validity
            self.assertEqual(results[0].status, CheckStatus.PASS)

            # Check 2: Lockfile missing
            self.assertEqual(results[1].status, CheckStatus.WARNING)
            self.assertIn("No lockfile detected", results[1].message)

            # Check 3: node_modules missing
            self.assertEqual(results[2].status, CheckStatus.WARNING)
            self.assertIn("node_modules directory is missing", results[2].message)

    def test_valid_package_with_lockfile_and_node_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "package.json").write_text(json.dumps({"name": "test-pkg", "version": "1.0.0"}), encoding="utf-8")
            (td / "package-lock.json").write_text("{}", encoding="utf-8")
            (td / "node_modules").mkdir()

            results, pkg_data = run_files_checks(td)
            self.assertIsNotNone(pkg_data)
            self.assertEqual(len(results), 3)
            self.assertTrue(all(r.status == CheckStatus.PASS for r in results))


if __name__ == "__main__":
    unittest.main()
