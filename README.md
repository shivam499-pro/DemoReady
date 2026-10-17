# DemoReady 🚀

**DemoReady** is a pre-flight developer tool designed for hackathons, team reviews, and live demonstrations. It statically inspects your Node.js project to verify that it is properly configured and ready to demonstrate.

Built for **No Hands: The Wispr Challenge** (WeMakeDevs & Wispr Flow).

---

## 🔒 Safety & Accuracy Guarantees

1. **Non-Destructive & Passive by Default**:
   - Never modifies scanned repositories.
   - Never runs `npm install`, build scripts, or unvetted code automatically.
2. **Zero Secret Leakage**:
   - Environment variable inspections compare **variable names only**.
   - Secret values in `.env` files are **never** displayed, printed in errors, logged, or serialized into JSON.
3. **Honest Endpoint Verification**:
   - Static health route detection is strictly identified as static code inspection.
   - It is never reported as proof that the server is live or functioning.
   - Live endpoint verification is distinctly reported as `NOT_CHECKED`.
4. **Controlled Test Execution**:
   - Tests are skipped by default (`NOT_CHECKED`).
   - `npm test` runs **only** if the user explicitly supplies `--run-tests`.
   - Timeouts are strictly enforced (`--test-timeout`, default 30s) to prevent hanging demo processes.

---

## 📋 Checks Performed

| Check Name | Category | What is Checked |
| :--- | :--- | :--- |
| **Target Path Validation** | Filesystem | Verifies the directory exists and is a valid folder. |
| **package.json Presence & Validity** | Required Files | Validates JSON syntax and root structure. |
| **Lockfile Presence** | Required Files | Detects `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, or `bun.lockb`. |
| **Dependencies Directory** | Required Files | Checks if `node_modules` exists. |
| **Environment Configuration** | Environment | Detects `.env` and `.env.example` presence. |
| **Environment Variable Parity** | Environment | Compares expected vs configured variable names (**never printing values**). |
| **Static Health Endpoint Definition** | Endpoints | Scans source files for `/health`, `/status`, or `/ping` route definitions. |
| **Live Endpoint Verification** | Endpoints | Accurately recorded as `NOT_CHECKED` during static inspection. |
| **Test Script Configuration** | Testing | Verifies a real test runner is configured in `scripts.test` (flags placeholder default scripts). |
| **Test Command Execution** | Testing | Opt-in execution via `--run-tests` with timeout enforcement. |

---

## 🚦 Status Indicators

- **`[PASS]`**: The check passed all criteria.
- **`[WARNING]`**: Non-fatal issue detected (e.g., missing `node_modules`, missing lockfile, general API without dedicated health endpoint). Actionable fix provided.
- **`[FAIL]`**: Fatal issue detected (e.g., missing or malformed `package.json`, missing required `.env`, placeholder test script).
- **`[NOT_CHECKED]`**: Explicitly skipped (e.g., un-requested test execution or live network probing).

---

## 🛠️ Installation & Setup

DemoReady is built entirely with the Python Standard Library (requires Python 3.9+).

```bash
# Clone the repository
git clone https://github.com/your-username/wispr-DemoReady.git
cd wispr-DemoReady

# Install in editable mode
pip install -e .
```

---

## 💻 Usage

### 1. Basic Inspection (Terminal Report)
Scan the current directory:
```bash
demoready
```

Scan a specific project path:
```bash
demoready --path ./path/to/node-project
```

### 2. JSON Output (CI / Automation Mode)
```bash
demoready --path ./path/to/node-project --json
```

### 3. Opt-in Test Execution with Timeout
Safely execute `npm test` with a 15-second timeout:
```bash
demoready --path ./path/to/node-project --run-tests --test-timeout 15
```

---

## 🧪 Running Automated Tests

DemoReady comes with a comprehensive automated test suite testing malformed inputs, missing files, secret-leakage protection, timeouts, and CLI output:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
