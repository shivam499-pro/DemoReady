# DemoReady 🚀

**DemoReady** is a pre-flight developer CLI tool designed for hackathons, team reviews, live demonstrations, and CI evaluation. It statically inspects Node.js repositories to verify that project files, dependencies, environment configurations, endpoints, and test commands are properly configured for demonstration—without modifying code, executing unvetted scripts, or leaking secrets.

Built for **No Hands: The Wispr Challenge** (WeMakeDevs & Wispr Flow).

---

## 💡 What Problem DemoReady Solves

Live demos and hackathon evaluations frequently fail due to preventable configuration mistakes:
- Missing `.env` files when `.env.example` specifies required variables.
- Missing `node_modules` or missing lockfiles.
- Unconfigured default test scripts (`echo "Error: no test specified" && exit 1`).
- Lack of a dedicated `/health` or `/status` route for liveness verification.
- Inappropriate checks applied uniformly (e.g., failing a reusable npm library because it lacks a `/health` endpoint or `.env` file).

DemoReady provides **instant, evidence-based pre-flight validation** with zero configuration required.

---

## 🔒 Security Guarantees & Technical Limitations

### Guarantees
1. **Passive & Non-Destructive**:
   - DemoReady never modifies files within the target repository during inspection. Filesystem writes occur only when the user explicitly specifies `-o` / `--output` to save an inspection report.
   - Never automatically executes `npm install`, build scripts, or arbitrary code.
2. **Zero-Secret Leakage**:
   - Environment checks inspect **variable names only**.
   - Values in `.env` and `.env.local` are **never** printed to the console, logged, or serialized into JSON reports.
3. **Controlled Test Execution**:
   - Test execution is disabled by default (`NOT_CHECKED`).
   - `npm test` runs **only** when explicitly requested via `--run-tests`, guarded by an enforced timeout (`--test-timeout`, default 30s).
4. **Honest Status Reporting**:
   - Static route detection is clearly labeled as static code analysis.
   - Live endpoint probing is distinctly recorded as `NOT_CHECKED`.

### Limitations
- **Static Heuristics**: Endpoint detection uses pattern matching for standard HTTP route declarations (e.g., Express, Fastify, Koa, NestJS, Next.js). It is not a full JavaScript AST parser and does not evaluate dynamically constructed route paths.
- **Pre-Flight Configuration Only**: A `READY` status confirms that expected configuration files, dependencies, scripts, and routes exist. It does **not** guarantee runtime application correctness, absence of runtime bugs, or external service availability (databases, external APIs).

---

## 🏷️ Supported Project Types

DemoReady includes a deterministic project classifier ([`demoready/core/classifier.py`](demoready/core/classifier.py)) that tailors checks to the project category. To prevent false positives, classification follows strict priority and requires **multiple independent signals** before classifying a project as a web application:

| Project Type | Classification Criteria | Check Applicability |
| :--- | :--- | :--- |
| **`WEB_SERVICE_OR_APP`** | Requires $\ge 2$ independent signals (e.g., `"private": true`, server start script (`start`/`serve`), deployment config (`Dockerfile`, `Procfile`, `render.yaml`), web framework in dependencies (`express`, `fastify`, `next`, etc.)). | All checks active: environment files, static health endpoint, lockfile, testing. |
| **`REUSABLE_LIBRARY`** | Npm publication metadata (`module`, `types`, `exports`, `publishConfig`, `prepublishOnly`) without server start scripts or deployment files. | Environment and endpoint checks are **`NOT_APPLICABLE`** (libraries are configured by callers, not `.env` files). |
| **`CLI_TOOL`** | Contains `"bin"` field in `package.json` and CLI dependencies (e.g., `commander`, `yargs`), without server deployment files. | Health endpoint checks are **`NOT_APPLICABLE`**. Environment checks are **`NOT_APPLICABLE`** unless a `.env.example` template is present. |
| **`MONOREPO_ROOT`** | Contains `"workspaces"` field or root monorepo config (`pnpm-workspace.yaml`, `lerna.json`, `turbo.json`, `nx.json`). | Endpoint checks are **`NOT_APPLICABLE`** at the monorepo root. Environment checks are **`NOT_APPLICABLE`** unless a template is present. |
| **`UNCLEAR`** | Sparse or conflicting evidence. Handled conservatively without assumptions. | Endpoint and environment checks run in safe discovery mode (missing `.env` yields `NOT_CHECKED` rather than fatal failure). |

---

## 🚦 Check Statuses, Readiness, & Exit Codes

### Check Status Meanings

- **`[PASS]`**: Check criteria were fully satisfied.
- **`[WARNING]`**: Non-fatal finding that should be reviewed before demo (e.g., general API routes detected without a dedicated `/health` endpoint, or uncommitted `.env.example` template for existing `.env`). Actionable fix is provided.
- **`[FAIL]`**: Fatal blocker for demonstration (e.g., invalid/missing `package.json`, `.env.example` defined but no `.env` present, or unconfigured test command). Actionable fix is provided.
- **`[NOT_CHECKED]`**: Check was deliberately skipped by policy (e.g., live endpoint verification, test execution without `--run-tests`, or environment checks on unclear projects with no env files).
- **`[NOT_APPLICABLE]`**: Check does not apply to this project type (e.g., health endpoint checks for a reusable library or CLI tool).

### Overall Readiness Statuses

- **`[READY FOR DEMO]`**: No failures and no warnings. All applicable pre-flight checks passed or were skipped safely.
- **`[READY WITH WARNINGS]`**: One or more warnings were detected, but zero fatal failures. Project can likely run, but configuration gaps exist.
- **`[NOT READY FOR DEMO]`**: One or more fatal failures (`FAIL > 0`) were detected.

### CLI Exit Codes

- **`0`**: Inspection completed and project is ready (`READY` or `READY_WITH_WARNINGS`).
- **`1`**: Inspection completed but project is not ready (`FAIL > 0`).
- **`2`**: Command-line invocation or filesystem error (e.g., invalid argument value, nonexistent output directory).

---

## 🛠️ Prerequisites & Installation

### Prerequisites
- **Python 3.9+** (DemoReady is built using the Python Standard Library).
- Node.js project to inspect (Node.js runtime is optional for static inspection; only required if using `--run-tests`).

### Setup

```bash
# 1. Clone the repository (replace <repository-url> with your repository URL)
git clone <repository-url>
cd wispr-DemoReady

# 2. Install DemoReady in editable mode
pip install -e .

# Or run directly without installation via Python module syntax:
python -m demoready.cli --help
```

---

## 💻 CLI Usage

```
usage: demoready [-h] [-p PATH] [--json] [--run-tests]
                 [--test-timeout TEST_TIMEOUT] [-o OUTPUT] [-v]
```

### 1. Basic Inspection
Scan the current directory:
```bash
demoready
```

Scan a specific project path:
```bash
demoready --path ./path/to/my-node-app
# or
demoready -p ./path/to/my-node-app
```

### 2. JSON Output (Stdout)
Emit structured JSON to stdout for pipes and command substitution:
```bash
demoready -p ./path/to/my-node-app --json
```

### 3. File Output for CI Automation
Save the JSON report directly to a file using `-o` or `--output`:
```bash
# Automatically implies --json, keeps stdout clean, and prints confirmation to stderr
demoready -p ./path/to/my-node-app -o report.json
```

### 4. Opt-In Test Execution
Safely execute `npm test` with custom timeout (default is 30 seconds):
```bash
demoready -p ./path/to/my-node-app --run-tests --test-timeout 15
```

---

## 🔍 Walkthrough Examples

### Example 1: Realistic Sample Web Application

DemoReady includes a pre-configured sample app at [`fixtures/realistic_sample_app`](fixtures/realistic_sample_app) containing an Express backend, `.env` parity, and a `/health` route.

Run the inspection:
```bash
demoready --path fixtures/realistic_sample_app
```

**Representative Terminal Output:**
```text
=== DemoReady Inspection: C:\wemakedev\wispr-DemoReady\fixtures\realistic_sample_app ===
----------------------------------------------------------------------------------------
[PASS]             package.json Validity: Valid package.json found (project: wispr-express-service, version: 1.0.0).
[PASS]             Lockfile Presence: Lockfile detected: package-lock.json.
[PASS]             Dependencies Directory: node_modules directory found.
[PASS]             Environment Variable Parity: All 4 variable(s) defined in .env.example are present in .env + .env.local.
[PASS]             Static Health Endpoint Definition: Static health route pattern detected in src/server.ts (heuristic match). Note: This is static code detection only and does not verify runtime availability or HTTP response.
[NOT_CHECKED]      Live Endpoint Verification: Live endpoint verification skipped. Static analysis cannot guarantee server availability without running a live server probe.
[PASS]             Test Script Configuration: Configured test command: "vitest run --passWithNoTests".
[NOT_CHECKED]      Test Command Execution: Test execution skipped by default. Provide --run-tests to execute.
----------------------------------------------------------------------------------------
Summary: 6 PASS, 0 WARNING, 0 FAIL, 2 NOT_CHECKED, 0 NOT_APPLICABLE
Readiness: [READY FOR DEMO]
```

**Representative JSON Output (`--json`):**
```json
{
  "target_path": "C:\\wemakedev\\wispr-DemoReady\\fixtures\\realistic_sample_app",
  "timestamp": "2026-10-18T09:36:53.589205+00:00",
  "readiness_status": "READY",
  "project_type": "WEB_SERVICE_OR_APP",
  "summary": {
    "PASS": 6,
    "WARNING": 0,
    "FAIL": 0,
    "NOT_CHECKED": 2,
    "NOT_APPLICABLE": 0
  },
  "checks": [
    {
      "name": "package.json Validity",
      "category": "required_files",
      "status": "PASS",
      "message": "Valid package.json found (project: wispr-express-service, version: 1.0.0).",
      "source_location": {
        "file": "package.json"
      },
      "details": {
        "name": "wispr-express-service",
        "version": "1.0.0"
      }
    },
    {
      "name": "Environment Variable Parity",
      "category": "environment",
      "status": "PASS",
      "message": "All 4 variable(s) defined in .env.example are present in .env + .env.local.",
      "source_location": {
        "template_file": ".env.example",
        "env_files": ".env, .env.local"
      },
      "details": {
        "inspected_files": [".env", ".env.local"],
        "configured_variable_names": ["DATABASE_URL", "JWT_SECRET", "LOG_LEVEL", "PORT"],
        "extra_variable_names": []
      }
    },
    {
      "name": "Static Health Endpoint Definition",
      "category": "endpoints",
      "status": "PASS",
      "message": "Static health route pattern detected in src/server.ts (heuristic match). Note: This is static code detection only and does not verify runtime availability or HTTP response.",
      "source_location": {
        "file": "src/server.ts"
      },
      "details": {
        "matching_files": ["src/server.ts"],
        "detection_type": "static_regex_heuristic"
      }
    }
  ]
}
```

---

### Example 2: Reusable Library (`NOT_APPLICABLE` Handling)

When inspecting a reusable library (e.g., an npm package exposing utility functions or Express middleware with `"types": "dist/index.d.ts"` and `"exports": "./dist/index.js"`):

```bash
demoready --path ./my-reusable-library
```

**Illustrative Terminal Output:**
```text
=== DemoReady Inspection: /projects/my-reusable-library ===
----------------------------------------------------------
[PASS]             package.json Validity: Valid package.json found (project: my-reusable-library, version: 1.0.0).
[PASS]             Lockfile Presence: Lockfile detected: package-lock.json.
[PASS]             Dependencies Directory: node_modules directory found.
[NOT_APPLICABLE]   Environment Configuration: Environment variable checks are not applicable to reusable library packages. Libraries are configured by their callers via options or constructor arguments, not by .env files.
[NOT_APPLICABLE]   Static Health Endpoint Definition: Health endpoint checks are not applicable to Reusable Library projects (not a persistent web service or application).
[NOT_APPLICABLE]   Live Endpoint Verification: Live endpoint verification is not applicable to Reusable Library projects.
[PASS]             Test Script Configuration: Configured test command: "vitest run".
[NOT_CHECKED]      Test Command Execution: Test execution skipped by default. Provide --run-tests to execute.
----------------------------------------------------------
Summary: 4 PASS, 0 WARNING, 0 FAIL, 1 NOT_CHECKED, 3 NOT_APPLICABLE
Readiness: [READY FOR DEMO]
```

**Why this matters**: A reusable package is not penalized for lacking a web server health endpoint or `.env` file. DemoReady identifies the library context and marks those checks `NOT_APPLICABLE`.

---

## 🧪 Running the Test Suite

DemoReady includes unit tests, regression tests, and integration tests covering all checks, formatters, and edge cases:

Run with Python's built-in `unittest`:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Or run with `pytest`:
```bash
python -m pytest
```

---

## 📂 Repository Structure

```text
wispr-DemoReady/
├── demoready/
│   ├── checks/
│   │   ├── endpoints.py      # Static route & health endpoint detection
│   │   ├── environment.py    # Secret-safe .env / .env.example parity analysis
│   │   ├── files.py          # package.json, lockfile, & node_modules checks
│   │   └── tests_config.py   # Test runner validation & opt-in test execution
│   ├── core/
│   │   ├── classifier.py     # Deterministic project classifier (5 project types)
│   │   ├── models.py         # CheckResult, CheckStatus, & InspectionReport models
│   │   └── runner.py         # Inspection orchestrator
│   ├── formatters/
│   │   ├── console.py        # Colorized & aligned terminal formatter
│   │   └── json_formatter.py # Machine-readable JSON serializer
│   └── cli.py                # Command-line entry point & argument parser
├── fixtures/
│   └── realistic_sample_app/ # Realistic Node.js Express service for validation
├── tests/                    # Comprehensive unit and integration test suite
└── pyproject.toml            # Project packaging specification
```
