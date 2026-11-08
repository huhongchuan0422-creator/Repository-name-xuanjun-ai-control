# Independent bootstrap — incomplete security candidate

CLI accepts controller-preopened file descriptors. It never imports or executes carrier code; on success it reserves nonce and prints VERIFIED_RESERVED. There is no installer in this version. Root-owned trust input is mandatory in CLI, as are root-owned ledger and log. Controller must create SQLite database in WAL mode with `CREATE TABLE operations(nonce TEXT PRIMARY KEY, task TEXT NOT NULL, attempt TEXT NOT NULL, state TEXT NOT NULL)` and maintain trusted directory/parent permissions. The controller must supply verified descriptors from protected paths; `open_relative` implements nofollow path traversal for integration. Ed25519 public key is base64 raw 32-byte; signed bytes are compact sorted-key ASCII JSON of receipt payload. Test keys must be marked TEST_ONLY. The digest allowlist mode pins SHA-256 of the canonical receipt payload, not a self-supplied carrier digest.

Not deployable: ledger path race and parent protections, crash reconciliation/state transition, log/ledger atomicity, safe extraction/installation, rollback, and production controller binding remain to be designed/tested. A VERIFIED_RESERVED output is not authorization to execute. No controller key is supplied.

## Experimental controller checkpoint

`controller.py` connects verification, nonce reservation and isolated staging/current symlink switch. It does not execute carrier code. This is an experimental fixture, not an install candidate: no rollback, startup reconciliation integration, concurrent attempt uniqueness enforced by schema, controller-owned stable database path, tool scope, service integration, or independent security review. The CLI invokes this experimental path and must not be used against a real deployment. A crash can leave RUNNING until the controller explicitly calls recover.

## Controller hardening checkpoint

Ledger parent must be private and controller owned; an absolute path is required.
The signed receipt now requires `tool_scope` (`mode`: READ_ONLY or WRITE_ALLOWED,
`tools`: mapping of names to exact resource strings), and the manifest must
carry a matching subset. READ_ONLY permits only fixed read-tool names. This is
an installation gate only; it does not enforce runtime MCP authorization. A
20-process test checks that one reservation succeeds for an identical attempt.
This is still not the full production path contract: ancestor directory and
SQLite path races, recovery evidence and rollback are not yet resolved.

## Deployment trust contract and SQLite preflight

Ledger and audit must each be in a controller-only directory owned by the
controller service uid and with no group/other access; all ancestors must be
owned by root or controller and not writable by group/other. Carrier service
identity must be distinct and unable to traverse these directories. Production
platform admission must verify account exclusivity, directory uid/gid/mode,
ACLs, mounts and service sandbox. Filesystem mode checks alone cannot establish
absence of ACL grants or malicious processes sharing the controller uid. A
process acting as the controller uid is in the trusted computing base; its
compromise is outside this boundary. These deployment facts remain unverified.

The carrier manifest requires `minimum_sqlite: [3,35,0]`. Bootstrap refuses
older SQLite before reservation. Tests of other paths on SQLite 3.26 override
only the reported version for fixture coverage, not compatibility evidence.

## Experimental reconciliation schema

The controller-provisioned operations table must also contain TEXT columns
`prestate_target`, `prestate_hash`, `staging_target`, `manifest_hash`,
`intended_target`, `receipt_hash`. The private root must begin with `current`
pointing at a private directory containing `.bootstrap-manifest.json`. The
controller locks `.bootstrap.lock`, reconciles pending rows before install,
and holds on ambiguous evidence. Success receipts are controller-owned files
whose digest and expected fields are pinned in the ledger. Their credibility
assumes the controller-only UID/directory contract above; they are not signed
external authority receipts. A crash between switching current and persisting
the success receipt hash deliberately stays UNKNOWN for independent review.
Reconciliation compares the stored manifest file digest, not every installed
file; complete tree-content verification remains a release blocker. This is
still experimental and must not be used for production installation.

## File-descriptor provenance contract

`FD_PROVENANCE=TRUSTED_CONTROLLER_OPENER`: binding, lock, trust, archive and
receipt descriptors must be opened by the authenticated controller identity
and its configured UID/GID, using component-wise dirfd/openat with O_NOFOLLOW.
An untrusted caller must not supply descriptors. Bootstrap validates the open
regular inode, link count, owner/mode, bytes, digest and signature; it cannot
and need not infer whether a descriptor was previously opened via a symlink.
The identity and opener contract must be bound by the independently authenticated
controller trust configuration and confirmed by platform admission.
