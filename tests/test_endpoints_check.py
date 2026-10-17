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


if __name__ == "__main__":
    unittest.main()

