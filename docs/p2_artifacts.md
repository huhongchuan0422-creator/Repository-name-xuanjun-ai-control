# P2 isolated artifacts installer

Scope: `ISOLATED_TEST_ONLY`. The component does not authorize production installation, read production registries, use signers, or issue/consume Grants.

Use `python -m production.p2_artifacts execute < request.json`, `inspect`, or `recover`. Python API: `execute(request)`, `inspect(request)`, `recover(request)`.

The request uses schema 1 and contains `scope:"ISOLATED_TEST_ONLY"`, installation/batch/attempt IDs, a dedicated absolute `root`, and `inputs` with operation `install`, absolute archive path, exact archive SHA-256, and a filename-to-SHA-256 manifest.

## Safety and persistence

The source archive is opened with `O_NOFOLLOW` and copied through that protected file descriptor into a mode-0400 component-owned snapshot. Device/inode/size/mtime are checked across the copy and the exact snapshot digest is checked before tar parsing. Validation and extraction then use only that snapshot, so replacing the source path after the open cannot change installed bytes.

Only manifest-listed regular tar members are accepted. Absolute/traversal names, links, devices, duplicate/unlisted members, oversized members, more than 2048 members, more than 512 MiB total extracted content, and archives larger than 768 MiB are rejected. Files are installed with bounded streaming writes and per-file SHA-256 verification.

State is under `root/.p2_artifacts/{journals,receipts,snapshots,recoveries,errors}`; version data is under `root/versions/<installation_id>--<batch_id>`. Component directories must be owned by the effective user, mode 0700 and not links; record files are created with no-follow/exclusive semantics. The caller-owned root must be owned by the effective user and cannot be group/world writable.

Receipts are immutable create-once records. COMMITTED is returned only after rereading and verifying journal, version files, receipt and any recovery evidence. Errors after root validation are persisted with a stable error code, operation stage and local evidence path; logs do not include request secrets.

## Recovery

`recover` is an actual current-batch reconciliation operation, not a retry alias. It verifies or recreates the exact protected snapshot, binds the journal to the request digest, inventories the current batch version directory and refuses unknown files or wrong hashes. Files already present with correct hashes are preserved; only missing manifest-owned files are restored from the exact snapshot. It then writes immutable recovery evidence and, only after full verification, the final receipt. Unknown ownership, conflicting bytes, corrupt/tampered journal, snapshot or recovery evidence returns HOLD. Other committed batch directories and receipts are never removed or replaced.

NO_EFFECT means there is no journal, receipt, current-attempt snapshot, version directory or recovery evidence for this batch. A protected snapshot left by interruption without a journal is treated as a recoverable current-batch effect, not NO_EFFECT.

## Limits

Isolation from another privileged process that can rewrite the component root cannot be guaranteed by this module alone. Tar compression bombs are bounded by extracted/member limits, but resource limits of the containing Docker environment remain the outer protection. This component does not manage processes or host services and never operates the UK production installation.
