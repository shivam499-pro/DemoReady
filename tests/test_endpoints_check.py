"""Unit tests for endpoint detection and live-verification honesty."""

from pathlib import Path
import tempfile
import unittest

from demoready.checks.endpoints import run_endpoints_checks
from demoready.core.models import CheckStatus


class TestEndpointsCheck(unittest.TestCase):
    def test_empty_project_no_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_endpoints_checks(Path(tmpdir))
            self.assertEqual(len(results), 2)
            # Static check should be NOT_CHECKED
            self.assertEqual(results[0].status, CheckStatus.NOT_CHECKED)
            self.assertIn("No JavaScript/TypeScript source files", results[0].message)
            # Live verification should be NOT_CHECKED
            self.assertEqual(results[1].status, CheckStatus.NOT_CHECKED)
            self.assertIn("Live endpoint verification skipped", results[1].message)

    def test_static_health_route_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            (src_dir / "server.ts").write_text(
                'import express from "express";\n'
                'const app = express();\n'
                'app.get("/health", (req, res) => res.json({ status: "ok" }));\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)

            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.PASS)
            self.assertEqual(static_check.name, "Static Health Endpoint Definition")
            # Verify requirement 1: Must not claim that the endpoint is running or works live
            self.assertIn("static code detection only", static_check.message.lower())
            self.assertIn("does not verify runtime", static_check.message.lower())

            live_check = results[1]
            self.assertEqual(live_check.status, CheckStatus.NOT_CHECKED)
            self.assertEqual(live_check.name, "Live Endpoint Verification")

    def test_general_api_without_health_route_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            (src_dir / "api.js").write_text(
                'app.get("/api/users", (req, res) => res.json([]));\n'
                'app.post("/api/items", (req, res) => res.status(201).end());\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)

            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.WARNING)
            self.assertIn("General API/server routes detected", static_check.message)
            self.assertIn("no dedicated /health", static_check.message)
            self.assertIsNotNone(static_check.fix)

    def test_real_javascript_commonjs_health_route(self):
        """Verify real JavaScript CommonJS file with app.get('/health', ...) is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            server_js = td / "server.js"
            server_js.write_text(
                "const express = require('express');\n"
                "const app = express();\n"
                "app.get('/health', (req, res) => {\n"
                "    res.status(200).json({ status: 'ok', uptime: process.uptime() });\n"
                "});\n"
                "app.listen(3000);\n",
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)
            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.PASS)
            self.assertIn("server.js", static_check.message)
            self.assertIn("static code detection only", static_check.message.lower())

    def test_javascript_health_route_trailing_slash_and_versioned(self):
        """Verify trailing slash and versioned API health route patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "index.js").write_text(
                "app.get('/api/v1/health/', (req, res) => res.send('OK'));\n",
                encoding="utf-8",
            )
            results = run_endpoints_checks(td)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertIn("index.js", results[0].message)

    def test_file_based_javascript_health_route(self):
        """Verify file-based routing such as routes/health.js is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            routes_dir = td / "routes"
            routes_dir.mkdir()
            (routes_dir / "health.js").write_text(
                "module.exports = (req, res) => res.json({ status: 'ok' });\n",
                encoding="utf-8",
            )
            results = run_endpoints_checks(td)
            self.assertEqual(results[0].status, CheckStatus.PASS)
            self.assertIn("routes/health.js", results[0].message)

    def test_source_location_health_route_pass(self):
        """Regression 4: health-route PASS result carries source_location with the
        exact matched relative file path.  The static-heuristic disclaimer must still
        be present in the message, and source_location must only contain the path —
        never file contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            (src_dir / "server.ts").write_text(
                'app.get("/health", (req, res) => res.json({ status: "ok" }));\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.PASS)

            # source_location must be present with the correct relative path
            self.assertIsNotNone(static_check.source_location)
            self.assertEqual(static_check.source_location["file"], "src/server.ts")

            # source_location must not contain file contents
            loc_value = static_check.source_location["file"]
            self.assertNotIn('app.get', loc_value)
            self.assertNotIn('res.json', loc_value)

            # Static-heuristic disclaimer must still be present
            self.assertIn("static code detection only", static_check.message.lower())

        # WARNING branch (no health route): source_location must be absent
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "api.js").write_text(
                'app.get("/api/users", (req, res) => res.json([]));\n',
                encoding="utf-8",
            )
            results_warn = run_endpoints_checks(td)
            self.assertEqual(results_warn[0].status, CheckStatus.PASS if False else CheckStatus.WARNING)
            self.assertIsNone(results_warn[0].source_location)

    def test_health_route_reference_in_test_directory_or_file_ignored(self):
        """Verify that health route references in test directories or spec/test files
        are ignored and do not falsely satisfy the health endpoint check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            # Production source only has general routes, no health route
            (src_dir / "api.js").write_text(
                'app.get("/api/users", (req, res) => res.json([]));\n',
                encoding="utf-8",
            )
            # Test file inside src/
            (src_dir / "api.spec.ts").write_text(
                'describe("api", () => { it("mocks", () => request(app).get("/health")); });\n',
                encoding="utf-8",
            )
            # Test file in dedicated test/ directory
            test_dir = td / "test"
            test_dir.mkdir()
            (test_dir / "health.test.js").write_text(
                'const res = await request(app).get("/health");\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)
            static_check = results[0]
            # Must be a WARNING because no real health route exists in production source
            self.assertEqual(static_check.status, CheckStatus.WARNING)
            self.assertIn("General API/server routes detected", static_check.message)
            self.assertIn("no dedicated /health", static_check.message)
            self.assertIsNone(static_check.source_location)

    def test_real_health_route_detected_with_coexisting_test_files(self):
        """Verify that a real health route in application source is detected
        even when test files co-exist and point to src/server.ts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            # Real health route in application source
            (src_dir / "server.ts").write_text(
                'import express from "express";\n'
                'const app = express();\n'
                'app.get("/health", (req, res) => res.json({ status: "ok" }));\n',
                encoding="utf-8",
            )
            # Coexisting test file in tests/ directory
            tests_dir = td / "tests"
            tests_dir.mkdir()
            (tests_dir / "server.test.ts").write_text(
                'request(app).get("/health").expect(200);\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)
            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.PASS)
            self.assertIsNotNone(static_check.source_location)
            # Source location must point to the production source file, NOT the test file
            self.assertEqual(static_check.source_location["file"], "src/server.ts")

    def test_prefix_test_files_and_spec_directories_ignored(self):
        """Verify prefix-style test files (test_*.js, test-*.ts) and spec/ directories
        do not falsely satisfy the health check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            # General routes only in production
            (src_dir / "api.js").write_text(
                'app.get("/api/products", (req, res) => res.json([]));\n',
                encoding="utf-8",
            )
            # Prefix-style test files inside src/
            (src_dir / "test_health.js").write_text(
                'request(app).get("/health");\n',
                encoding="utf-8",
            )
            (src_dir / "test-health.ts").write_text(
                'request(app).get("/health");\n',
                encoding="utf-8",
            )
            # Nested spec directories
            spec_dir = td / "spec" / "nested"
            spec_dir.mkdir(parents=True)
            (spec_dir / "health_check.js").write_text(
                'request(app).get("/health");\n',
                encoding="utf-8",
            )
            specs_dir = td / "specs" / "e2e"
            specs_dir.mkdir(parents=True)
            (specs_dir / "status.ts").write_text(
                'request(app).get("/status");\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)
            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.WARNING)
            self.assertIn("General API/server routes detected", static_check.message)
            self.assertIn("no dedicated /health", static_check.message)
            self.assertIsNone(static_check.source_location)

    def test_production_files_like_protest_and_contest_not_accidentally_skipped(self):
        """Verify that genuine production files containing 'test' or 'spec' in their
        names (protest.ts, contest.js, special.ts, routes/health.js) are scanned normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            src_dir = td / "src"
            src_dir.mkdir()
            routes_dir = td / "routes"
            routes_dir.mkdir()

            # Production file with 'test' substring
            (src_dir / "contest.js").write_text(
                'app.get("/api/contest", (req, res) => res.json({ contest: true }));\n',
                encoding="utf-8",
            )
            # Production file with 'spec' substring
            (src_dir / "special.ts").write_text(
                'app.get("/api/special", (req, res) => res.json({ special: true }));\n',
                encoding="utf-8",
            )
            # Production file defining health
            (src_dir / "protest.ts").write_text(
                'app.get("/health", (req, res) => res.json({ status: "protest-ok" }));\n',
                encoding="utf-8",
            )
            # Standard route file
            (routes_dir / "health.js").write_text(
                'module.exports = (req, res) => res.json({ status: "routes-health-ok" });\n',
                encoding="utf-8",
            )

            results = run_endpoints_checks(td)
            self.assertEqual(len(results), 2)
            static_check = results[0]
            self.assertEqual(static_check.status, CheckStatus.PASS)
            self.assertIsNotNone(static_check.source_location)
            # All valid production files should be scanned; health routes detected
            matching_files = static_check.details.get("matching_files", [])
            self.assertTrue(any("protest.ts" in f for f in matching_files))
            self.assertTrue(any("routes/health.js" in f or "routes\\health.js" in f for f in matching_files))

    def test_skipped_test_files_do_not_consume_scan_limit(self):
        """Verify that skipped test files (both in test dirs and in src/) do not count toward max_files."""
        from demoready.checks.endpoints import scan_source_files

        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # 1. Create 10 test files in test/ and spec/ directories
            test_dir = td / "test"
            test_dir.mkdir()
            for i in range(5):
                (test_dir / f"test_{i}.js").write_text(f"// test {i}\n", encoding="utf-8")

            spec_dir = td / "spec" / "unit"
            spec_dir.mkdir(parents=True)
            for i in range(5):
                (spec_dir / f"spec_{i}.js").write_text(f"// spec {i}\n", encoding="utf-8")

            # 2. Create 10 prefix and dot-test files directly in src/
            src_dir = td / "src"
            src_dir.mkdir()
            for i in range(5):
                (src_dir / f"test_service_{i}.js").write_text(f"// prefix test {i}\n", encoding="utf-8")
                (src_dir / f"service_{i}.test.ts").write_text(f"// dot test {i}\n", encoding="utf-8")

            # 3. Create 2 genuine source files (one with health route)
            (src_dir / "api.js").write_text('app.get("/api/data", () => {});\n', encoding="utf-8")
            (src_dir / "server.ts").write_text('app.get("/health", () => {});\n', encoding="utf-8")

            # Total files in tree = 22. With max_files=5, if test files counted, we'd hit the limit before scanning src/
            health_matches, has_api, has_sources = scan_source_files(td, max_files=5)
            # Both genuine source files must have been scanned
            self.assertTrue(has_sources)
            self.assertTrue(has_api)
            self.assertIn("src/server.ts", health_matches)

    def test_existing_ignored_directories_still_work(self):
        """Verify that existing ignored directories (node_modules, dist, build, .git, .next, coverage, .turbo, .cache)
        are ignored and do not falsely trigger health check PASS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # Put health route definitions inside all standard ignored directories
            ignored_dirs = [
                "node_modules/pkg/lib",
                ".git/hooks",
                "dist/bundle",
                "build/static",
                ".next/server",
                "coverage/lcov-report",
                ".turbo/cache",
                ".cache/build",
            ]
            for d in ignored_dirs:
                target_dir = td / Path(d)
                target_dir.mkdir(parents=True)
                (target_dir / "health.js").write_text('app.get("/health", () => {});\n', encoding="utf-8")

            # Target only has general api routes in src/
            src_dir = td / "src"
            src_dir.mkdir()
            (src_dir / "app.js").write_text('app.get("/api/items", () => {});\n', encoding="utf-8")

            results = run_endpoints_checks(td)
            static_check = results[0]
            # Since health files in ignored directories are skipped, status must be WARNING
            self.assertEqual(static_check.status, CheckStatus.WARNING)
            self.assertIsNone(static_check.source_location)


if __name__ == "__main__":
    unittest.main()



