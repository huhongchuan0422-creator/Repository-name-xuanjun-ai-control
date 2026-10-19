# P2 isolated artifacts installer

Scope: `ISOLATED_TEST_ONLY`. This component does not authorize production installation, read production registries, use signers, issue/consume Grants, control systemd, use the Docker socket, or read production configuration.

Runtime target for this node is the existing container **Python 3.11**. CI also verifies Python 3.12. The UK host may remain on Python 3.6.8; this component does not require or authorize upgrading host Python.

## Interface

CLI:

```sh
python3.11 -m production.p2_artifacts execute < request.json
python3.11 -m production.p2_artifacts inspect < request.json
python3.11 -m production.p2_artifacts recover < request.json
```

Python:

```python
from production.p2_artifacts import execute, inspect, recover
result = execute(request)
```

Complete acceptance request example:

```json
{
  "schema": 1,
  "scope": "ISOLATED_TEST_ONLY",
  "installation_id": "acceptance-001",
  "batch_id": "artifact-batch-001",
  "attempt_id": "attempt-001",
  "root": "/work/p2-artifacts-acceptance",
  "inputs": {
    "operation": "install",
    "archive": "/work/input/artifact-batch-001.tar",
    "archive_sha256": "64_hex_char_sha256",
    "files": {
      "bin/worker": "64_hex_char_sha256",
      "plugins/example.py": "64_hex_char_sha256"
    },
    "modes": {
      "bin/worker": 448,
      "plugins/example.py": 384
    }
  }
}
```

Mode values are decimal JSON integers: **384 = 0600** and **448 = 0700**. Only those two file modes are accepted. Files default to 0600 when omitted from `modes`. Executables must therefore be explicitly declared as 0700; the installer verifies the installed mode before COMMITTED, so it cannot report success while a declared executable is non-executable. Directories are component-owned 0700.

## Safety and persistence

The source archive is opened with `O_NOFOLLOW` and copied through that protected file descriptor to an attempt-owned partial snapshot. Device/inode/size/mtime are checked across the copy and the exact expected SHA-256 is required. Only after these checks is the mode-0400 snapshot atomically published. Validation and extraction use only that snapshot. Concurrent writes to the opened source are rejected and cannot create a successful receipt; source-path replacement after a completed snapshot cannot change installed bytes.

Only manifest-listed regular tar members are accepted. Absolute/traversal names, links, devices, duplicate/unlisted members, oversized members, more than 2048 members, more than 512 MiB total extracted content, and archives larger than 768 MiB are rejected. Files are written to attempt-owned partial files with bounded streaming SHA-256 verification, correct mode is fsynced, and the verified file is published without overwriting an existing target.

State is under `root/.p2_artifacts/{journals,receipts,snapshots,recoveries,errors}`; version data is under `root/versions/<installation_id>--<batch_id>`. Component directories must be owned by the effective user, mode 0700 and not links. The caller-owned root must be owned by the effective user and cannot be group/world writable.

Receipts are immutable create-once records. COMMITTED is returned only after rereading and verifying the journal, installed hashes and modes, receipt, and any recovery evidence. Errors after root validation are persisted with stable error code, operation stage and evidence reference.

## Crash recovery acceptance sequence

1. Prepare the dedicated 0700 root and exact archive/manifest request.
2. Run `execute`. A normal run returns COMMITTED only after the installed state and immutable receipt verify.
3. Run `inspect` with the identical request. It must return the same COMMITTED receipt.
4. For crash testing, SIGKILL the CLI in one of these windows: while the protected snapshot `.partial` is being copied; while an attempt-owned `.p2-part-<attempt_id>` file is being streamed; or immediately after the immutable receipt appears but before the original CLI exits.
5. Start a new process and run `recover` with the identical request.
6. Recovery records hashes of owned interrupted partials in the error evidence area before removing those partials. It preserves already-correct files and restores only missing files from the exact digest-bound snapshot. Unknown files, wrong existing bytes/modes, unowned partials, corrupt journal/snapshot/recovery evidence return HOLD.
7. Run `inspect` again and verify COMMITTED. Compare the previous committed batch directory and receipt byte-for-byte/inode/mtime as appropriate; recovery of the new batch must not change them.

The CI acceptance tests execute all three SIGKILL windows in independent child processes and restart the CLI for recovery. They also perform a real concurrent source mutation during snapshot creation and require HOLD, no success receipt, and retained failure evidence.

## Recovery semantics

`recover` is current-batch reconciliation, not an unconditional retry. A SIGKILL during snapshot creation may leave only the exact current-attempt partial snapshot. Recovery records its path, size and SHA-256 as crash evidence, removes that owned partial, and recreates the protected snapshot from the request's exact expected digest. A SIGKILL during a file write may leave an exact attempt-named partial file; recovery records and removes only that owned partial. Correctly published files are not overwritten. If the receipt was already durably published, recovery performs verified idempotent readback and leaves the receipt and installed files unchanged.

Other committed batches are never removed, replaced or rolled back.

## Limits

A privileged process that can rewrite the component root is outside this module's isolation boundary. Container filesystem/resource policy remains the outer resource boundary. No UK production installation is performed by this component or its CI.
