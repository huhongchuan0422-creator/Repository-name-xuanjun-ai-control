# Saved finite-probe evidence export, r6

FEATURE_ID: P2_RETAINED_RECOVERY

This is one fixed saved-data export. The exporter authenticates the existing r6 kit, successful observation 1311b9e9fa97cfd4, its diagnostic receipt, the exact nonce-scoped probe receipt, and the three installed preparation sources. It does not collect a new observation, execute a probe, invoke preparation, change permissions, fetch approvals, or grant installation authority.

The original drop-in metadata is embedded with its exact integer timestamps and SHA256 7412f8e70c998cf6fd8cedcbc444c0715747ff7421e49910c08d66cec43df7b7. It is not freshly sampled. The unchanged frozen topology projector runs against the full private observation in memory. A separate strict schema rejects unknown fields, private strings, malformed resources/events, incomplete cases, and unsafe cleanup evidence before output. No redaction is used to claim an exact evidence hash.

The output contains all eight validated cases, policy, Node proof, server events, exact receipt metadata and canonical receipt bytes, original drop-ins, topology bytes, proof-input hashes and the unsigned expected review body. Output is bounded to 512 KiB. Whole-observation hashes are explicitly host-authenticated bindings: the subset cannot independently reproduce the entire private observation. Ancillary acceptance is reported from the successful preparation; that full validation is not rerun by this exporter.

The protected read/projection stage and output stage have separate 60-second recurring alarms. The delivery bootstrap has a separate 30-second download bound. Sudo/interpreter startup and uninterruptible kernel calls are outside these cooperative deadlines. Unknown cleanup is HOLD. A possibly partial output is never retried automatically.

## Independent offline verification

Run from this directory with the complete exported JSON saved as a file:

    python3 -I -B -S verify_exported_evidence.py export.json ../artifacts/epoch7-kit-0c8a0f2a.tar.gz ../preparation-source-r6-contracts/epoch7_topology_projection.py

The verifier authenticates the pinned archive and source, validates the exact public subset, and recomputes policy, input, receipt, evidence, drop-ins, topology and expected-review-body hashes. It reports whole_observation_recomputed=false. A PASS is evidence consistency, not an independent approval or host execution authorization.

## Public tests and repository layout

The top-level tests/test_p2_saved_probe_evidence_r6.py adapter reads only its exact pinned public fixtures plus the published r6 archive. It authenticates all 250 archive members, materializes a disposable local layout, then runs 33 orchestration, 14 strict-schema and 23 mocked-bootstrap tests. The existing preparation-source-r6-contracts wrapper/data/projector/projector-test files are reused as public fixtures. The unchanged production functions are exercised only with synthetic inputs; no real host methods run.

The adapter has six tests, including source tamper/alias, archive tamper, unexpected materialization and workflow checks. The dedicated read-only workflow runs this exact top-level file under -I -B -S in a private ACL-checked checkout. Test child process groups, log sizes and deadlines are bounded; deliberately escaped sessions and uninterruptible kernel calls are outside that cleanup guarantee.

The bootstrap template intentionally refuses an unset publication commit. A later delivery copy may bind the actual immutable commit; it uses the exact known /usr/libexec/platform-python3.6 interpreter. No actual host export has run at this checkpoint.
