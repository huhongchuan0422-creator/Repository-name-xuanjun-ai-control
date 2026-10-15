# Consolidated Owner diagnostic: local review candidate

Status: **NOT APPROVED, NOT PUBLISHED, NOT RUN ON UK.** This is a separate
wrapper candidate. It does not alter the frozen kit, manifest, extractor, source
index or production code. It is not an installation-ready or approved command.

## Deliverable and local evidence

- `owner_diagnostic.py`: standalone Python3.6-compatible wrapper candidate.
  SHA256 `93c891542b6eb77da05e665ce56cbfe97918a2c09c66b2a90720107f13d28968`.
- `test_owner_diagnostic.py`: SHA256
  `b1d81c1fe2851771c8c4bccaa81f78de2c321883dded784a1c57dcd88e8531ec`.
- `python368-tests.log` and `python312-tests.log`: **66/66 PASS**, zero skips.
  These are local fixtures and mocked boundaries. They include real protected
  local receipt writes/readback, the real233-file frozen archive inspection,
  exact source hashes, symlink/authority/zero-write refusal, download scope,
  one-case selection, skip/failure handling and sanitized error behavior.
- `cached-selection-python368.log` and `cached-selection-python312.log`: real
  final-kit cached import and exact one-case discovery succeeded on both
  interpreters. **The fixed-UID case body was not executed.**
- No network request, UK command, systemd probe, production ACL change or resume
  ran to prepare or test this candidate. The wrapper's real host outcome is
  **NOT_VERIFIED**. `local-evidence.json` binds the explicit deliverable files.

## Fixed reviewed public inputs

The wrapper accepts no source URL, hash, host, directory, suite or command
override. Its only network destinations are these two public HTTPS objects:

1. Extractor at source commit
   `3b87d10b66ae791086cdb05a554ad44ed0f4ad90`, path
   `evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py`.
   SHA256 `bb387213e7d1c2b36472161d564aabd6ec02dc59601c9f14df91915d14541134`,
   exactly9579 bytes.
2. Archive at artifact commit
   `7aeb2fc006f99e9aa9360cb8225ceea550eb92c8`, path
   `evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-3b87d10b.tar.gz`.
   SHA256 `3a54f554b4a6477e094853773135e6aabfe508d6c0c3ba8e9623c0ea8d25abac`,
   exactly946844 bytes.

Both use `https://raw.githubusercontent.com/` and repository
`huhongchuan0422-creator/Repository-name-xuanjun-ai-control`, with the full
immutable commit and exact path. Parent source/publication readbacks established
these references; this wrapper has not fetched them locally or on UK.

Entry SHA256 is
`13fd850d6a6cc0b8199af1d0c579318d401fda6e6a1d9de0dbed0e91983a14e8`;
kit manifest SHA256 is
`01dc59516509435def70b5c3d10ba1cb1f97f2d1ba87f61695e856eefd80800c`.
The manifest must identify helper source3b87 and tree
`89ea6a31d5159c4dc7932baf06653455a2203f7e` with232 declared files.
The unchanged full-kit CI evidence is1704 mandatory plus157 bootstrap cases,
zero skips. Those results are separate from this new66-case wrapper evidence.

## Required review and Owner prerequisites

1. Review this wrapper and its tests, including its intentional direct invocation
   of the separately classified fixed-UID test. Independently authenticate its
   exact bytes before execution from protected root-owned storage. The wrapper
   and trusted interpreter/stdlib are bootstrap trust; it cannot authenticate
   external consent or its own initial execution.
2. Identify the actual trusted UK Python executable and use `-I -B -S`. Do not
   invent an interpreter hash or substitute a user-writable Python. The wrapper
   requires EUID/EGID0 and the fixed short hostname
   `iZd7oeikknn1z21sq6ji6zZ`. An existing ITIMER_REAL alarm is refused.
3. The existing protected parent is exactly
   `/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520`.
   Root-owned/root-group, no-symlink, non-writable-by-group/other and no-ACL
   ancestry must pass the unchanged readers. The wrapper does not create or
   repair this parent, host locks, permissions, accounts or installed sources.
4. Select a new16-lowercase-hex observation identifier. Both corresponding
   observation and diagnostic filenames must be absent. For the finite probe,
   also select a fresh32-lowercase-hex random nonce and review its exact resource
   scope. Existing nonce directories, receipts or runtime unit files are refused.
   The probe separately refuses loaded collisions and validates its own receipt.
5. The host must reach the two fixed public HTTPS objects with normal TLS
   validation and no proxy/redirect. The extractor is fetched even when the kit
   already exists; there is no offline fallback or transport retry. No credential
   or private host evidence is sent in these fixed public requests.
6. Obtain explicit Owner action-time approval for the selected diagnostic
   effects. The optional finite probe specifically requires approval of the
   ledger capability/syscall scope, actual account clones, Node operation,
   global daemon-reloads and cleanup limits below. Flags are acknowledgements;
   they neither supply that approval nor grant recovery permission.

No final command is supplied as ready or approved: actual interpreter validation,
secure wrapper delivery, independent wrapper review, fresh identifiers and the
Owner's exact action-time approval remain outstanding.

## Single invocation interface and order

The argument contract is `--observation-id` plus
`--execute-reviewed-diagnostic`. Add both `--nonce` and
`--execute-reviewed-probe` only for the separately approved finite probe.
Unknown arguments, incomplete nonce/flag combinations and omitted diagnostic
acknowledgement fail before host collection or downloads. There is no resume
option, private-plan input, approval override or arbitrary path option.

1. Check fixed host/root/isolation; download and authenticate the fixed extractor
   in memory before executing it. Reject redirects, proxy configuration, encoding
   changes, bad status, length or hash; make no retry. TLS validation remains on.
2. Verify protected parent and absent output/nonce paths. If the exact kit
   directory is absent, download/hash-check the archive and call the unchanged
   strict extractor. If present, strictly verify it instead. No overwrite,
   repair, partial-tree cleanup or unsafe tar extraction is used.
3. Authenticate the entry bytes, verify the entire exact kit and provenance,
   then create its byte-identical authenticated disposable test copy.
4. Load the fixed test and its declared import closure from verified cached
   bytes. Run exactly
   `test_epoch7_exact_access_uk.ActualFDTests.test_actual_fd_acl_changes_only_two_named_access_sets`.
   Require one test, zero errors/failures/skips. Its source SHA256 is
   `8984cdc5a77411051fb9c2d9d81aefcd8c662e206c14f25dfa90c349f6512635`.
   The manifest remains unchanged and disabled for the general test CLI.
   Remove only the owned disposable copy and reverify the original kit.
5. Call the frozen `kit.observe` exactly once. An ordinary failed/skipped ACL
   case still permits fresh read-only metadata collection, but blocks the
   optional probe. A source-integrity/fixture-cleanup boundary exception stops
   collection. Any snapshot HOLD blocks the probe inside the frozen entry.
6. Reverify the original kit, then write one new0600, fsynced, readback-verified
   diagnostic receipt. Print only fixed statuses, counts and hashes. Failure
   produces a nonzero result; no raw host evidence or exception text is printed.

## Exact effects and evidence limits

Without the probe, effects are limited to an optional new protected kit tree,
one temporary authenticated test copy, ACL changes on its two synthetic targets,
and two new private output files. The observation opens existing install and
activation locks read-only and takes nonblocking exclusive flocks; it releases
them and performs bounded read-only metadata/command collection. It does not
start services or alter production configuration. Private evidence can contain
sensitive source/host material and must remain on the protected host.

The fixed-UID test needs kernel mappings covering1002,1003,1004 and POSIX ACL
support on that filesystem. It applies release-traversal named grants to its
synthetic directory and UID1003 read access to its synthetic client file, verifies
the exact xattrs, unchanged bytes/owners and one-shot refusal. It does **not**
impersonate those accounts or prove final production DAC/Owner authorization.

The optional probe creates `/run/xj-p2-proof-<nonce>/` and exactly six runtime
systemd units: one socket and ledger/broker/dashboard/callback/native services.
It performs two **global daemon-reloads**, plus exact nonce start/stop/restart
operations. Existing accounts are used without NSS changes; no unit is enabled.
Only the ledger clone receives the reviewed CAP_SYS_PTRACE, with ptrace,
process_vm_readv and process_vm_writev denied and tested against own synthetic
children. The probe exercises eight bounded socket cases, actual role/read-path
and SDK checks, peer/namespace observations and one builtin-only in-memory Node
SQLite diagnostic. No production database, network/model call or OpenClaw import
is part of those probe effects.

Downloads have30-second stage alarms and10-second transport timeouts. Extraction,
verification and the exact fixture stage have60-second initial alarms. Their
KeyboardInterrupt-derived timeout escapes unittest error capture; periodic
one-second delivery remains armed during owned context cleanup. Each final kit
reverification has its own60-second stage. Primary interruption/error is
preserved if cleanup or reverify also fails, with a separate fixed failure flag.
A deadline can leave the owned disposable copy for review; no automatic cleanup
retry follows. The collector
uses its unchanged600-second cooperative deadline and bounded local queries;
there is deliberately no outer alarm during `kit.observe`, since the probe
refuses an already armed timer. The probe supplies its own60-second watchdog,
15-second cleanup, bounded manager/transport calls and five-second Node child.
Synchronous kernel/NSS calls are not claimed to be hard-preemptible; this wrapper
does not promise a global hard wall-clock limit.

Cleanup only touches owned, matching nonce resources and confirms processes are
gone. It intentionally retains the nonce root and protected consumed receipt
for subsequent authenticated composition. Changed/unknown resources remain HOLD.
SIGKILL, power loss, default SIGTERM outside the probe or an uninterruptible
kernel call can leave partial effects. A partial kit/output remains in place for
review. There is no automatic retry, claim reset, nonce reuse, broad cleanup or
fallback to a different source. A passing diagnostic is not installation admission.

## Consolidated local audit corrections

The initial60-test candidate had two confirmed defects: unittest caught its
one-shot timeout as an ordinary error, leaving later cleanup without a running
alarm; and a failed final reverify could replace the primary interruption.
Both are corrected as described above. New real-alarm tests cover a slow test,
slow cleanup and slow reverify; paired-failure tests preserve the primary
KeyboardInterrupt/error. The original60-test logs and pre-audit receipt are
retained. Independent scoped rereview of these exact revised bytes confirmed both fixes;
the reviewer independently reran the six new real-alarm/paired-failure cases
on each interpreter,6/6 PASS. No additional blocker was confirmed in that
scoped review. This is code-review evidence, not Owner action-time approval. These
corrections affect only this separate wrapper candidate, not any frozen kit file.

## Complete remaining recovery path

Keep the original private observation, its finite-probe attempt and the protected
nonce receipt. Supply the eleven finite private seed fields: observation,
current compiled retained binding with measured control.git reconciliation,
two exact identity-policy payloads, matching additive deltas, explicit renewal
timer decision, and six byte-preserved retained buffers (native, TLS journal,
prior provisioning, legacy units, publisher journal, sandbox candidate).
The loader supplies the five authenticated-cache fields itself.

The real factory must return COMPILED_NOT_ADMITTED with no unresolved inputs.
Freeze the exact approved plan and private seed as separate root0600 files,
bind their exact hashes and the computed host/resource/live-control contracts,
and obtain a genuine fresh schema2 PR58 complete approval. Only the existing
protected resume entry may then call the coordinator once; this wrapper cannot.
Fresh preflight, machine approval, claims, effect guards and containment remain
coordinator-owned. Independent production and Owner/business acceptance still
follow execution. All these host/approval/acceptance gates remain pending.
