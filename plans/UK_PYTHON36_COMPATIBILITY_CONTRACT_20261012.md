# UK P2/P3 Python runtime compatibility contract (Owner mandate, 2026-10-12)

**Status: development-source policy; not installed on the UK host.**
**Mandatory host baseline: Python 3.6.x, as reported by Owner; runtime patch level and interpreter hash require host-side verification.**
This is a constraint, not permission to upgrade Python or change production services. Governs UK P2, P3, #19 bootstrap, installer, rollback, task ledger, callback, dashboard and all Python scripts launched by UK Runner or systemd.

## Version decision

1. **DO NOT replace** `/usr/bin/python3`, `/usr/bin/python`, change alternatives, change the global PATH, rebuild existing venvs, install distro Python packages, or upgrade host Python as a shortcut. Python 3.7 is EOL (2023-06-27) and no longer a worthwhile upgrade target; Python 3.6 is also EOL and must be treated as a legacy runtime risk.
2. Preserve the currently installed host interpreter and the exact interpreters used by every existing systemd unit and GitHub Runner script. All new **UK-host Python code** must run on **Python 3.6.x** until separate version-isolated migration approval and evidence exist.
3. GitHub-hosted CI scripts may explicitly use a newer Python, but they must be labeled `GITHUB_HOSTED_ONLY` and must not be copied to or run under the UK Python 3.6 runtime without full compatibility acceptance. Such CI PASS does not prove real UK compatibility.
4. Future modernization, if necessary, must install a supported interpreter **side by side**, under a dedicated immutable path and isolated venv/container. Do not repoint system Python. Record dependency-lock hashes, library/ABI availability, per-unit executable paths, backup/rollback and whole-system canary. Prefer a currently supported CPython version based on verified OS/toolchain support, not 3.7.
5. No Python version change may be admitted on a PR comment alone. Privileged install and existing service migration require an exact reviewed, hash-bound Owner package and independent host acceptance.

## Code-generation restrictions — hard blockers before proposing installation

- No features introduced later than 3.6, such as `dataclasses`, `contextvars`, `datetime.datetime.fromisoformat`, `asyncio.run`, `subprocess.run(text=True)`, `subprocess.run(capture_output=True)`, `pathlib.Path.is_relative_to`, `zoneinfo`, assignment expressions (`:=`), `match`, built-in `list[str]`, and `str.removeprefix`. This list is illustrative, not exhaustive.
- Syntax must be accepted by an **actual pinned Python 3.6 interpreter** (grammar-only parse from a newer Python is diagnostic and cannot replace it); standard-library API availability and dependencies must be verified under the same interpreter.
- Use only verified dependencies/stdlib and Python 3.6-compatible third-party release pins. Check shared-library ABI, wheels, imported packages, package manager behavior and venv shebangs.
- Make runtime path explicit. For the current UK environment use **`/usr/bin/python3`** for preflight and systemd unless preflight proves that unit points to another approved, pinned interpreter. Interpreter identity must be rechecked before install and at canary.
- Treat unverified `python3` in PATH, `#!/usr/bin/env python3`, or tests run only on a CI-hosted Python 3.12+ as **NOT_VERIFIED** for UK. Never claim UK_36_PASS from a local developer 3.13 AST parse.
- Maintain model/OAuth controls unchanged: only `openai/gpt-5.6-sol`, `fallbacks=[]`, existing OAuth; never call a model to run Python version diagnostics.

## Required gates before every UK Python installation

**Read-only preflight**: prove `/usr/bin/python3` resolved path/realpath, version+patch level and binary SHA256; record `ExecStart`/shebang for all affected units without changing them. Preserve the original interpreter state.

**Same-interpreter verification**: run Python 3.6 syntax/static tests, actual runtime import and package probes and the complete bounded regression in an isolated/test directory with no production/credential access. Compare the executable hash at testing and runtime. Run `python3 -B` for import-based test flows when avoiding pyc writes; never treat mere `ast.parse(feature_version=(3,6))` as runtime proof.

**Release**: Python 3.6 compatibility must be a named independent QA gate, and Security/Release must bind to the exact same code and manifest hashes. Unknown or failed host proof => `HOLD_PY36_COMPATIBILITY_NOT_VERIFIED` or `FAIL_PY36_INCOMPATIBLE`; do not auto-upgrade Python, suppress tests or switch interpreter.

**Rollback**: before any later side-by-side migration, retain all old `ExecStart` paths, dependency locks, unit/config hashes and direct immutable backups. Verify rollback with no dual worker/writer, no lost checkpoint or modified canonical ledger.

## Existing artifacts and cautions

- The owner-supplied P2 mechanical canary V3 tarball was built for UK 3.6; historical assistant-side checks included Python 3.6 grammar and offline tests run on another interpreter. **Real UK Python 3.6 execution was not yet evidenced**.
- The proposal branch contains `scripts/uk-external-runner-watchdog.py`, which uses `datetime.fromisoformat`, a Python 3.7+ API. It is intended for **GitHub-hosted** CI Python 3.12 and **must not** be deployed on UK Python 3.6 in that form. `stage1/uk_quota_policy.py` uses an explicit Python-3.6-compatible timestamp parser; still needs real host tests.
- No upgrade, restart, reinstall or system unit mutation occurred by publishing this document. Current P2/P3 remains HOLD until real platform evidence.

## Source references
- Python 3.7 EOL: https://peps.python.org/pep-0537/
- Python 3.7 porting changes: https://docs.python.org/3/whatsnew/3.7.html
- Red Hat warning against changing system Python: https://docs.redhat.com/en/documentation/Red_Hat_Enterprise_Linux/10/html/installing_and_using_dynamic_programming_languages/changing-the-python3-interpreter-on-rhel

**Acceptance state now:** `UK_PYTHON_BASELINE=3.6_OWNER_REPORTED`; `UK_PYTHON_RUNTIME_VERIFIED=NO`; `PYTHON37_SYSTEM_UPGRADE=DENY`; `UK_P2_P3_COMPATIBILITY_GATE=HOLD_UNTIL_REAL_PY36_TEST`.
