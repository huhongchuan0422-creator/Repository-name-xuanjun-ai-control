# P2 isolated process runtime

Scope: **ISOLATED_TEST_ONLY**. This component manages only processes it starts inside an ordinary Linux container. It does not control the host, consume Grants, or connect to production stores, signers, registries, Docker sockets, systemd, or external networks.

## API

Python:

```python
from p2_runtime import execute, inspect, recover
```

CLI:

```sh
python production/p2_runtime/__init__.py execute --request request.json
python production/p2_runtime/__init__.py inspect --request request.json
python production/p2_runtime/__init__.py recover --request request.json
```

All responses preserve the request identity fields and additionally expose:

- `config_sha256`: stable digest of argv, cwd, explicit env, health configuration and runtime timeout.
- `operation_id`: stable digest binding installation_id, batch_id, attempt_id and config_sha256.
- `commit_receipt`: immutable original COMMITTED start receipt reference once a start has committed.
- `receipt`: the current immutable action/observation receipt. Later observations never overwrite the original commit receipt.

## Startup validation

All start parameters are validated before the PREPARED journal is written and before any child process is created:

- structured argv only; shell executables are rejected;
- absolute executable and cwd;
- bounded environment and secret-looking environment names rejected;
- bounded operation timeout;
- complete health configuration validation;
- Unix Socket health path must be an absolute normalized path under this component's isolated root.

Invalid preflight input returns HOLD and creates no process journal.

## Process ownership and interruption recovery

A start writes PREPARED, then records leader PID, Linux start time, process-group ID, session ID, configuration identity, log path and collector identity. The process group is the batch cleanup boundary. PID/session/group mismatch returns HOLD and is never signalled.

STOPPING recovery may finish cleanup only after ownership is revalidated. PREPARED without sufficient post-launch evidence remains HOLD; it is never treated as NO_EFFECT and is never blindly restarted.

A vanished leader is not sufficient for NO_EFFECT while owned descendants or the log collector remain.

## Continuous bounded logging

The previously established independent log collector remains the log enforcement mechanism. It is a separate process from the management CLI. It enforces the fixed byte limit while the workload runs and terminates only the verified batch process group if the limit is exceeded.

Therefore, killing the management CLI does not disable log-size enforcement. Tests explicitly SIGKILL the CLI and verify that the collector still stops the over-limit batch while an earlier batch remains alive and its immutable receipt hash remains unchanged.

## Application readiness

Two health types are supported:

### Process liveness

```json
{"type":"process"}
```

This verifies process ownership/liveness only.

### Unix Socket protocol readiness

```json
{
  "type":"unix_socket",
  "path":"/isolated/root/app.sock",
  "request":"PING\n",
  "expect":"PONG\n",
  "connect_timeout":0.1,
  "read_timeout":0.1,
  "total_timeout":2.0,
  "max_response":256
}
```

Rules:

- AF_UNIX stream sockets only.
- No shell probe, TCP/HTTP probe, external network, or host service dependency.
- Connection timeout, read timeout and overall deadline are independently bounded.
- Response bytes are bounded by `max_response`.
- The exact expected UTF-8 protocol response must be received; process liveness alone does not count as application readiness.
- RUNNING state is re-probed during `inspect`, `recover`, and duplicate start reads.
- A live-but-not-ready process, timeout, bad response, oversized response, application exit, or ownership uncertainty yields HOLD.

## Immutable receipts

Each receipt has a unique append-only path. The original successful start receipt is persisted in the batch journal as `commit_receipt`. Later observations receive a new `receipt` and repeat the stable `operation_id`, `config_sha256`, and original `commit_receipt` reference.

The original receipt file is never overwritten, so a coordinator can retain and re-check its SHA256 independently of subsequent observations.

## Tests

```sh
python -B -m unittest discover -s tests/p2_runtime -p 'test_*.py' -v
```

Real-process coverage includes:

- process start/stop, child cleanup and cross-batch isolation;
- PID identity mismatch and STOPPING/PREPARED recovery;
- immutable receipts and configuration conflict detection;
- log-limit cleanup;
- Unix Socket normal readiness;
- live-but-not-ready, response timeout and incorrect response;
- application exit and readiness re-read by a new CLI process;
- management CLI SIGKILL with no killed-batch inspect/recover call, proving the independent collector still enforces log limits.

CI runs Python 3.11 and 3.12 in `.github/workflows/p2-runtime.yml`.

## Remaining limits

- Linux `/proc` and POSIX process groups/sessions are required.
- Unix Socket protocol readiness uses exact UTF-8 request/response matching only; no arbitrary executable probe hooks are accepted.
- Processes that deliberately escape the recorded process group/session cannot be safely reclaimed by this component.
- Filesystem ownership/mode protects the local journal; this is not a production cryptographic authority.
- No production Writer, AuthorityStore, Signer, Registry, shared database, Grant, or UK installation is involved.
