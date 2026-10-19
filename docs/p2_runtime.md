# P2 isolated process runtime

Scope: **ISOLATED_TEST_ONLY**. This component manages only processes it starts inside an ordinary Linux container. It never controls the host, consumes Grants, or connects to production stores/signers/registries.

## API

Python: `from p2_runtime import execute, inspect, recover` after adding `production` to `PYTHONPATH`.

CLI:

```sh
python production/p2_runtime/__init__.py execute --request request.json
python production/p2_runtime/__init__.py inspect --request request.json
python production/p2_runtime/__init__.py recover --request request.json
```

All methods use the same JSON identity fields: schema=1, scope=ISOLATED_TEST_ONLY, installation_id, batch_id, attempt_id, root and inputs. Start requires structured argv, absolute executable/cwd, explicit environment and process health configuration. Shell executables are rejected. Environment keys that look like secret/token/password/private/key material are rejected because the runtime does not accept secrets.

## Durable process ownership

A start persists PREPARED before launch, then records leader PID, Linux start time, process-group ID, session ID, complete configuration SHA256, environment SHA256, health SHA256, log path and observed process-group members. Processes are launched with a new session. Stop and failure cleanup signal only the recorded process group after verifying its current session/process identity; a reused/mismatched PID/group returns HOLD.

The process group is the cleanup boundary. A batch failure never enumerates or signals other groups. A vanished leader does not imply NO_EFFECT while verified members of the recorded group remain.

## Configuration identity

The configuration digest includes full argv, cwd, explicit env values and health configuration. Reusing the same attempt with any change returns `CONFIG_CONFLICT`. The journal stores argv and hashes of environment/health; callers must not place secrets in requests.

## Logs

Each batch owns one append-only log. Size is checked during initial health observation and on every later inspect/recover/duplicate execute. If the log exceeds the fixed bound, the journal enters STOPPING and the verified owned process group is terminated. A cleanup result that cannot be proven returns HOLD; the runtime never leaves a known over-limit process running and reports COMMITTED.

## Recovery

`inspect` and `recover` never launch or blindly restart.

- PREPARED without sufficient process identity evidence -> `START_OUTCOME_UNKNOWN` / HOLD.
- STOPPING + verified group gone -> journal advances to STOPPED and a committed recovery receipt is written.
- STOPPING + verified group alive -> `STOP_OUTCOME_UNKNOWN` / HOLD.
- RUNNING requires process-group/session identity and current log-bound health checks.
- PID/session/group mismatch or /proc uncertainty -> HOLD.
- STOPPED with the owned group proven gone -> NO_EFFECT.

## Receipts

Every receipt has a unique append-only path. COMMITTED action receipts and observation receipts are never overwritten. The returned SHA256 therefore remains valid after later inspect/recover calls.

## Tests

```sh
python -B -m unittest discover -s tests/p2_runtime -p 'test_*.py' -v
```

The suite uses real Linux processes for start/stop, process-group child cleanup, interrupted PREPARED/STOPPING recovery, PID identity mismatch, configuration conflicts, log overflow cleanup and cross-batch isolation. Python 3.11 and 3.12 run in `.github/workflows/p2-runtime.yml`.

## Remaining limits

- Linux `/proc`, POSIX sessions and process groups are required.
- Health checking is currently process-liveness only; application HTTP/TCP readiness is intentionally outside this component.
- Processes that deliberately escape the component's process group/session are unsupported and result in evidence limits rather than host-wide cleanup.
- The journal is protected by filesystem ownership/mode, not a production cryptographic authority.
- No systemd, Docker socket, host cgroup control, network dependency, production database, production Writer, Signer, Registry or Grant is used.
