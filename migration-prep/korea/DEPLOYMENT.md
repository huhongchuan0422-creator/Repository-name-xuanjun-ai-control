# Korea isolated deployment candidate

This directory is packaging input only. Nothing here installs a user, directory,
service, SecretRef, firewall rule, credential, or Writer until a separately approved
root transaction invokes `install-candidate.sh` on Korea.

## Self-contained delivery and default validation

Build and validate the exact extracted input from the repository root:

```text
PYTHONPATH=migration-prep python3.11 -m korea.build_runtime_candidate /root/private/runtime-candidate
python3.11 /root/private/runtime-candidate/migration-prep/korea/validate_runtime_candidate.py \
  /root/private/runtime-candidate --expected-manifest-sha256 <sha256>
```

The directory includes every declared Python dependency. Validation rejects
missing/extra bytes, normal or dangling symlinks, and uses `python -I` with only
the extracted `migration-prep` directory inserted. It cannot borrow workspace files
and performs no network call.

Before any mutation, install validates a root-private staging chain, the complete
manifest/import, existing identity attributes, root-owned target parents and every
target with both `-e` and `-L`. It copies to a private staging directory, validates
again, then atomically renames one content-addressed release. Its transaction record
binds the manifest/content, release, venv Python, unit and exact owned objects.
Check requires the exact transaction path and expected manifest SHA-256, then
verifies installed bytes, real current/venv identity, the disabled/inactive
service and effective unit/drop-ins. Re-entry succeeds only for the same valid
transaction. Uninstall requires the transaction hash and refuses replaced objects;
it retains state, credentials, evidence and identity. Failure reports its stage and
cleans only objects created by that attempt.

The candidate uses its own Python 3.11 virtual environment and dedicated service
identity. The systemd template keeps release/config read-only and state/log roots
writable. `ControlledHttpsTransport` is the only packaged HTTP transport: it has no
generic method API, ignores proxy environment variables through raw sockets, denies
redirects, pins resolved addresses, and requires normal TLS hostname/certificate
verification. The installed candidate remains valid but deny-all: its base unit has
`IPAddressDeny=any` and no `IPAddressAllow`. A separately reviewed Phase-C action
must create a root-owned drop-in with exact pinned addresses before any live GET.
The installation command never creates that drop-in and never starts the unit.

This still does not prove root-controlled egress or absence of every bypass in an
installed runtime. A destination firewall cannot inspect an encrypted HTTP method;
application GET enforcement and root network confinement are both mandatory and
must be independently audited after installation. No IP, unit or transport was
installed or exercised against Binance in this batch.

The business `snapshot_id` is selected inside the closed WAL-aware copy for the exact
account and freshness window; it is never the evidence-only `observation_run_id`.
The real entry uses the shared server-time/surface-window/pagination/state core,
independently verified raw network evidence and one overall capture deadline. PASS
exits 0, HOLD exits 2 and UNKNOWN exits 3.

The unit is wired to bounded continuous sampling. A separate acceptance config must
carry Owner-approved duration, interval, sample count, resource/latency thresholds,
approval id and window id. The checked-in template deliberately has
`owner_approved=false`, so it cannot execute acceptance. A hash-bound window ledger
binds the acceptance config, runtime config, artifact, account, database path,
verifier and snapshot-publisher identity. Restart is accepted only within the
Owner-approved restart count and maximum gap; expiry, a long gap, tested-object
drift or incomplete end coverage permanently holds that window. Every cycle requires
a fresh independently verified `XUANJUN_SQLITE_WAL_BACKUP_ATOMIC_HANDOFF_V1`
receipt for an atomically published, closed WAL-aware SQLite snapshot. A static copy
cannot satisfy a long window. Resource monitoring samples during each cycle,
includes cgroup peak/OOM evidence, and hard-stops immediately on a non-PASS status
or resource/latency threshold breach. Failed samples cannot be waived.
Template numbers are suggestions, not approvals. The candidate permits zero new
entries because no production Writer authority is packaged.

The refresh handoff is deliberately narrower than a scheduler or transfer agent.
An independently authorized source-side collector must reuse the existing
`ReadOnlyBusinessDatabase`/SQLite read-only backup path against the live WAL database
without freezing it, close and integrity
check the copy, and issue an independently verifiable receipt binding capture time,
account, publisher identity, runtime manifest and database SHA-256. A destination
publisher must verify those fields and atomically rename the closed copy and receipt
into the configured input paths. The Shadow process admits that generation only
after byte-hash and verifier checks. Neither collector nor publisher is installed,
scheduled or authorized by this candidate; absent that real route, continuous
acceptance remains HOLD rather than relaxing `snapshot_max_age_ms`.

Rollback is Korea-first: lock Korea Writer, revoke its credential, remove its IP,
reconcile every unknown outcome, and only then consider Tokyo restoration and a new
Tokyo epoch. Yibi, novel, PostgreSQL, Redis and either production Runner are outside
this artifact and must remain unchanged.

The handoff admission path opens the published closed generation with
`O_NOFOLLOW`, hashes and independently verifies that exact descriptor, and
materializes the bytes from the still-open descriptor into the private run
directory before SQLite backup/consumption.  Concurrent replacement of the
configured path therefore cannot pair generation A's receipt with generation
B's database.  A published path with `-wal` or `-shm` sidecars is incomplete
and is rejected rather than guessed or merged.

Resource acceptance requires explicit cgroup v2 `memory.peak` plus
`memory.events` evidence, or cgroup v1 `memory.max_usage_in_bytes`,
`memory.failcnt`, and `memory.oom_control` evidence.  Missing, unreadable, or
unsupported cgroup evidence is HOLD; RSS and a synthetic zero OOM count are
not substitutes.

Candidate tests do not prove Korea host installation compatibility, a real
publisher/verifier/Authority wiring, or a continuous Shadow window.  Those
remain separate post-install, independently witnessed acceptance gates.
# Transaction cleanup evidence

Failed candidate installation never authorizes a retry.  Cleanup removes only
objects and identities created by that exact attempt and still matching their
recorded identity.  Every removal is followed by a read-only residual check.
Object or account identity drift, deletion failure, lookup uncertainty,
remaining objects/identities, or daemon-reload failure produces
`CLEANUP=PARTIAL` with a retained-item list.  `CLEANUP=COMPLETE` means the final
checks found no attempt-owned residual; it is not inferred from ignored command
status.  This candidate behavior is test evidence only and does not authorize a
Korea installation.

Both successful installation and successful same-version re-entry pass through
one terminal-state finalizer.  It releases and verifies the attempt-owned lock
before setting the committed state or printing `STATUS=PASS`.  A retained or
identity-changed lock instead exits nonzero with `CLEANUP=PARTIAL`; on re-entry,
the pre-existing valid installation and transaction are preserved unchanged.


## 2026-10-16 real Phase-B host warning / false-success correction

Owner-root installed exact632bbe6f once under review6207630392; transaction
install-f887b085508e3ed4 SHA256c79182446ab8c2e447cb6942061710fb4a864addb4b9718f967402ef8c30cfe2.
The candidate is disabled/inactive/PID0 and the install lock was released.
This commits installation only: host security acceptance is HOLD. The actual
verify output reported unknown LoadCredential directives and no BPF/cgroup
firewall support, explicitly proceeding without firewalling. Exit0 and an
IPAddressDeny line did not establish enforcement; the former PASS must not be
used as a Phase-C or network-isolation approval.

The source correction adds a diagnostic-sensitive preflight before install
locks/identities/targets and the same refusal during installed checks. A private
synthetic unit uses /bin/true and /dev/null credential references; verify does
not start it, access a provider, import runtime or read real credential files.
All nonempty verify diagnostics fail closed, including zero-exit warnings.
NO_NETWORK in the old check describes the import self-check, not actual kernel
enforcement; the new output explicitly says RUNTIME_CONFINEMENT=NOT_EXERCISED.
Synthetic adapters test refusal/cleanup and do not establish host capability.

This patch is NOT a repair installer, compatible fallback unit, authorized
upgrade or proof that the old host can enforce isolation. Do not rerun the
new installer on the installed target; do not edit its release/unit/transaction
or stop existing business services. Preserve /root/pr99-phaseb-632bbe6f and the
old17-file release as evidence. No automatic cleanup or uninstall is proposed.

A complete minimal recovery remains pending actual host capabilities. Prefer
an offline-only private network namespace if the real kernel and unit manager
support it; test only a short-lived, no-packet child namespace through the
existing Owner-root terminal. Do not infer support from the directive text or
change global firewall/kernel/systemd. A fallback must bind exact unit and
transaction changes, existing-source hashes, backups, rollback/failure states
and continued disabled/inactive status in one review before deployment.
Credential delivery for Phase-C remains separate: removing an unsupported
LoadCredential line is not a credential-custody implementation. No Shadow,
exchange request, credentials, database copy, Finance/Writer or Tokyo action is
authorized. R2 lock-finalization and R6 approvals remain inherited; their code
is not rewritten for this compatibility issue.

Primary directive reference: https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml
LoadCredential was introduced in v247; PrivateNetwork is a different isolation
mechanism and is only a possible offline fallback, not yet accepted on this host.
