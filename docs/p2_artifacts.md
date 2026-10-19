# P2 isolated artifacts installer

Scope: `ISOLATED_TEST_ONLY`. This module is not a production installer, signer, Grant consumer, Registry reader, or host service manager.

From repository root, run `python -m production.p2_artifacts execute < request.json`; likewise `inspect` and `recover`. Python API: `from production.p2_artifacts import execute, inspect, recover`.

JSON request fields: `schema:1`, `scope:"ISOLATED_TEST_ONLY"`, `installation_id`, `batch_id`, `attempt_id`, `root` (existing, dedicated, absolute non-symlink directory), `inputs:{"operation":"install","archive":"/absolute/path.tar","archive_sha256":"<sha256>","files":{"app/file.py":"<sha256>"}}`.

Only regular files listed in the manifest are accepted. Archives must contain exactly those members; directories, links and device members are refused. Version files live under `root/versions/<installation_id>--<batch_id>/`. Journals and receipts are under `root/.p2_artifacts/`. Records are fsynced. `recover` is reconciliation only: incomplete or conflicting state returns HOLD, never repeats installation. Previously committed batches are never deleted.

Result statuses: COMMITTED is checked against on-disk files and journal/receipt; NO_EFFECT requires an absent journal, receipt and version directory; otherwise HOLD. Errors provide stable code and optional local journal path. No secrets are returned.

Limitations: caller must supply a dedicated root with filesystem isolation and trusted process ownership; this module does not defend against another privileged process concurrently changing its root, input archive, or parent directories. Interruption after journaling produces HOLD and requires operator-assisted reconciliation before new attempt. The archive is validated before writing and is expected to be immutable during the call. No production use is authorized.
