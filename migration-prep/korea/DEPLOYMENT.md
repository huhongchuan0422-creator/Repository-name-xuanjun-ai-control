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
