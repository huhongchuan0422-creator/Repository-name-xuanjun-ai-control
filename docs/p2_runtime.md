# P2 isolated process runtime

Scope: **ISOLATED_TEST_ONLY**. This module manages processes inside an ordinary Linux container only. It does not control the host or consume production permissions. All state is under a caller-created, owned, mode-0700 absolute root directory; do not point it at shared installation/artifact roots.

## API and CLI

Python: add `production` to PYTHONPATH; `from p2_runtime import execute, inspect, recover`. Each accepts a JSON-compatible dict and returns a result dict.

CLI: `python production/p2_runtime/__init__.py execute --request /path/to/request.json`; substitute `inspect` or `recover`. With no --request, reads stdin JSON. Exit 2 denotes HOLD.

Example:

```json
{
  "schema": 1,
  "scope": "ISOLATED_TEST_ONLY",
  "installation_id": "test-install",
  "batch_id": "batch-1",
  "attempt_id": "attempt-1",
  "root": "/tmp/privately-owned-runtime",
  "inputs": {
    "operation": "start",
    "argv": ["/usr/bin/python3", "-c", "import time;time.sleep(30)"],
    "cwd": "/tmp",
    "env": {},
    "health": {"type": "process"},
    "timeout": 0.2
  }
}
```

Stop: same identifiers with `"operation":"stop"`. A committed start requires reading /proc process start-time and group identity plus a timed process-alive check. `inspect` and `recover` do **not** launch or restart processes. Journal states PREPARED/STOPPING, inconsistent identity, and unknown outcomes return HOLD. Receipt includes absolute file path and SHA256; journal and receipt use replacement+fsync. Logs are per batch. Do not place secrets in argv or environment because journal stores argv (not environment values). Requests should never include secrets.

## Limits and known gaps

- Linux /proc required; no systemd, Docker socket, cloud credentials or network.
- Only process-alive health checks are implemented; no HTTP health or application-readiness probe.
- A process that daemonizes or spawns independent descendants is not supported; descendant cleanup/reaping is not established.
- Journals are not authenticated; root directory must be isolated from all untrusted principals.
- Exhaustive process identity and crash-window race testing, robust output log truncation, and guaranteed failure cleanup are **not yet established**. HEALTH_FAILED and LOG_LIMIT currently HOLD for inspection.
- No approval, signer, Grant, shared P2 ledger, database, or production activation.

Test: `python -B -m unittest discover -s tests/p2_runtime -v`.
