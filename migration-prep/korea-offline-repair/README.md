# PR99 Korea: complete offline Phase-B compatibility repair candidate

This is a NEW controlled repair candidate, not a production approval. Do not rerun
the original installer. Do not execute this helper before a new precise
independent action approval and Owner-root private admission are registered.

## Actual input and inherited evidence

- Original installed commit: `632bbe6f204a2c9ef778d3c91e425593c079abb1`.
- Original 17-file source/archive review, R2 and R6 are inherited unchanged.
- Approved original archive is included verbatim as a test/review fixture only:
  SHA256 `f7cba56c2c45910901cdbd44056ad7c971a7497ffe67518a4adefb40ef660ba9`.
- Original root transaction SHA256:
  `c79182446ab8c2e447cb6942061710fb4a864addb4b9718f967402ef8c30cfe2`.
- Actual root installation COMMIT and disabled/inactive/PID0 were reported by
  Owner, but security acceptance remains HOLD: systemd ignored LoadCredential
  and BPF IP filtering. Original apparent PASS is not security acceptance.
- Owner subsequently reported kernel `5.10.134-19.8.al8.x86_64`, systemd
  `239 (239-82.0.4.5.al8.5)`, and an ephemeral root `unshare --net` child with a
  distinct namespace and only `lo`; exit 0. This proves child namespace
  capability, not confinement of a started systemd service.
- Fail-closed diagnostics increment `94f8e10d` has Hosted 141/141 PASS;
  run38849018960/job116805878032. It is not a deployed compatibility repair.

## Minimal installed change

Only the fixed installed service unit and the `unit_sha256` field of the exact
existing transaction may change. The existing transaction ID, release, all 17
source files, original manifest, current symlink, user/group, venv, state/config
and log directories remain. No runtime reinstall, unlink, uninstall, chmod of
old content, kernel/systemd upgrade or global firewall modification is included.

`offline.service` uses `PrivateNetwork=yes` and `RestrictAddressFamilies=AF_UNIX`.
It removes unsupported LoadCredential, ineffective IPAddressDeny, credential
EnvironmentFile and network-online dependencies. Its entry is only the original
runtime's no-network `self_check`, explicitly imported with `-B -I`. There is
no continuous runner or business launcher. No credentials are provided. The unit
stays disabled/inactive/PID0. This profile cannot be promoted to Phase-C by
adding an IPAddressAllow drop-in: Phase-C needs a separately reviewed supported
credential custody/network/entrypoint design and execution permission.

The old template inside the preserved release is inert historical source. The
old installed checker is not the acceptance tool for this new profile; it still
expects the previous BPF text. Existing fresh-install candidate/guard are not
being deployed or claimed to support this old host. The repair's exact-byte,
manager-property and state checks govern this limited repair.

## Execution admission (before every persistent change)

Execution is only through the existing trusted Owner admin/root terminal. No
sudoers, arbitrary root runner grant, second queue or unattended host job is
added. CLI requires actual root and the exact Korea host, isolated Python and a
clean environment. Model-only adapters are import APIs; no CLI test bypass.

The reviewer must issue a NEW independent comment with this unique structured
body block. The developer must not issue or self-accept it:

```text
<!-- PR99_OFFLINE_REPAIR_APPROVAL_V1
{ "schema_version": 1,
  "action": "PR99_PHASE_B_OFFLINE_UNIT_REPAIR_V1",
  "host": "iZmj7a5kwr75qc1tul4kf9Z",
  "approval_comment_id": NEW_COMMENT_ID,
  "source_commit": "EXACT_40_HEX_COMMIT",
  "artifact_sha256": "ACTUAL_TAR_SHA256",
  "helper_sha256": "ACTUAL_HELPER_SHA256",
  "unit_sha256": "ACTUAL_OFFLINE_UNIT_SHA256",
  "old_transaction_sha256": "c79182446ab8c2e447cb6942061710fb4a864addb4b9718f967402ef8c30cfe2",
  "issued_at": INTEGER_UTC_EPOCH,
  "expires_at": INTEGER_UTC_EPOCH_NOT_MORE_THAN_12_HOURS_LATER,
  "max_attempts": 1,
  "service_start_allowed": false,
  "phase_c_allowed": false }
PR99_OFFLINE_REPAIR_APPROVAL_V1 -->
```

The review channel must give Owner the complete UTF-8 comment body SHA256.
Only trusted Owner-root registers `/etc/xuanjun-pr99-release` root:0700 and its
`offline-repair-admission.json` root:0600, containing `approval_comment_id`,
`approval_body_sha256` and the exact `approval_body`. This is the accepted
independent-review plus private-root-anchor trust model, not a cryptographic
reviewer signature. A developer PASS/comment or the spent old Phase-B approval
does not grant admission. The exact source commit, TAR bytes, helper/unit hashes,
host, action, old transaction, expiry, max-attempt and forbidden service start
are checked together. No network access is needed by the repair helper.

The archive and its extracted package must be root-owned private material in a
root:0700 non-writable path. The helper checks all archive members/byte hashes
and extracted bytes against `REPAIR_BINDING.json`; extra files, links and unsafe
paths fail. No mutable branch download is allowed for execution.

After approval, the eventual root invocation shape is:
`env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C /usr/bin/python3.11 -I -u /ROOT_PRIVATE_PACKAGE/controlled_repair.py --package /ROOT_PRIVATE_PACKAGE --archive /ROOT_PRIVATE_ARCHIVE`
This is documentation, not a currently approved command or grant.

## Single attempt and acceptance

1. Validate entire exact archive, extracted bytes and private root approval.
2. Exclude old installation lock; atomically acquire that same lock directory.
   Create/fsync permanent `/var/lib/xuanjun-pr99-offline-repair-v1` attempt and
   root:0600 bounded receipt. Any existing attempt prevents re-entry, including
   after success, partial write, expiry or process interruption.
3. Recheck exact old transaction/unit, all 17 source hashes, manifest, current,
   venv Python, disabled/inactive/PID0/no drop-ins and six named shared units.
4. Repeat one short no-packet netns child capability probe and reject all
   systemd verify diagnostics, even exit-zero warnings, on a synthetic unit.
5. Save/fsync old unit/transaction and shared metadata in the private attempt.
6. Recheck service/transaction/expiry, atomically replace unit, verify the real
   unit, then atomically change only the transaction's unit hash. No service
   start, enable, stop, restart, API, credentials, DB or network requests.
7. One daemon-reload. Verify effective manager PrivateNetwork=yes and AF_UNIX,
   original dedicated identity, no drop-ins, disabled/inactive/PID0, exact new
   unit/transaction, unchanged runtime/current/venv and shared unit metadata.
8. Verify and release only this attempt's original lock inode BEFORE PASS.
   Save exact final unit/transaction hashes and the constrained acceptance.

Runtime network confinement of a STARTED systemd service remains NOT_EXERCISED;
that is explicitly outside this Phase-B no-start scope. Root child capability
and manager recognition must not be reported as a started-service test.

Any warning, timeout, exception, SIGTERM, file/identity drift, reload ambiguity,
partial replacement, nonempty/replaced lock or missing receipt is HOLD. Preserve
all inputs/backups/staged files/lock/attempt, do not blindly rerun or automatically
roll back. After unit replacement failure the unit may be on disk but manager
still have old state; do not start it. After success the original runtime
template is still historical only. An emergency rollback would be a separately
approved stopped/offline action; no rollback/start action is shipped here.

## Tests and review boundary

`python3 -B -m unittest discover -s migration-prep -p test_korea_offline_repair.py -v`
executes the real repair transaction with disposable filesystem/syscall models
and the original approved 17 source bytes. It proves guard/order/byte preservation,
negative paths, partial writes/SIGTERM and terminal lock semantics in that model.
It is not real Korea root or systemd enforcement evidence. The existing Hosted
workflow builds the exact source-bound artifact only after its checks succeed;
its live host inspection job remains disabled.

Source review and this artifact do not grant execution. New precise approval,
Owner-root anchor and actual single repair receipt are still required. Production
migration, Phase-C, actual exchange GETs/trading/Writer/DB/custody, shared service
control and Tokyo retirement remain HOLD. PR99 remains Draft/unmerged. The
already-migrated website, DNS, Work content/current and PR122 are untouched.
