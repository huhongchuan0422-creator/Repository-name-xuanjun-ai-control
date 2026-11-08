# Development authority provider/reader v3

`development_authority_provider.py` is the formal loopback issuer. The
TEST_ONLY Task Center application neither exposes this route nor loads a formal
private key. Consumers receive only the pinned Ed25519 public key and must call
`verify_envelope` with values from trusted configuration and the actual request;
no expected value may be copied from the envelope being verified.

## Frozen installation

Formal runtime preflight is executable with
`python3 scripts/development_authority_runtime.py`; it requires Python 3.11+,
SQLite 3.40+ and exactly cryptography 42.0.8. The repository's SQLite 3.26 /
Python 3.6 compatibility environment is a migration fixture only and must fail
this formal preflight (exit 69). `requirements-authority.lock` is the formal
Python dependency pin.

Install an exact reviewed commit and tree (never a moving branch or `latest`),
record `git rev-parse HEAD HEAD^{tree}`, and pin the Python wheel/application
artifact by SHA-256. Before replacing anything, copy the prior executable,
service file, owner-only configuration, public trust bundle, and database backup
manifest to a dated owner-only rollback directory. Do not copy the private key.

The issuer configuration has exactly these fields:

```json
{
  "ledger_db": "/srv/xuanjun/formal/development.sqlite3",
  "forbidden_ledger_paths": [
    "/srv/xuanjun/test/task-center.sqlite3",
    "/var/lib/xuanjun/test/task-center.sqlite3"
  ],
  "forbidden_ledger_policy_file": "/etc/xuanjun/authority-forbidden-ledgers.json",
  "deployment_class": "formal-primary",
  "issuer": "xuanjun-formal-ledger",
  "instance_id": "development-authority-01",
  "version": "3.0.1",
  "anchor_id": "development-authority-2026-11",
  "service_id": "mcp-authority-reader",
  "bearer_token_file": "/etc/xuanjun/authority-reader.token",
  "private_key_file": "/etc/xuanjun/authority-ed25519.pem"
}
```

The source-frozen deployment class supplies a non-removable minimum TEST_ONLY
path set.  The owner-only policy file is separately signed by the pinned
deployment root and may add paths for that class; the signed provider config may
only append further paths.  An empty list, unrelated replacement, missing
built-in/policy path, wrong deployment class, or invalid policy signature fails
before the provider opens a ledger.  Independently, the opened inode is checked
against every path/alias and its runtime profile must be exactly `FORMAL`.

Configuration and secret files must be owner-only. Run the issuer as a distinct
OS identity with read-only ledger access and private-key access. Readers get the
corresponding public key, pinned issuer, instance, semantic version, anchor,
service identity and maximum age. The provider checks logical path, resolved
file, device/inode identity, link count and the inode actually opened by SQLite;
the TEST_ONLY ledger and any hardlink/symlink alias are rejected.

## Request and authorization

The authenticated request is exactly `task_id` plus a unique `request_id`.
The signed response binds issuer/instance/version, reader service identity,
task, attempt, lease, fence, epoch and resource-scope digest. A verifier also
checks schema/kind, signature, legal active task state, valid resource claims,
lease expiry against a trusted clock, revocation state and replay consumption.

HTTP 200 means only that a signed status query succeeded. Execution is allowed
only when `verify_envelope` returns successfully and `authority.authorized` is
exactly `true`. Reader rejection code **69 remains a rejection code**, never a
component identity or a success target.

`development_authority_reader.py` is the executable reference/probe. Every
verification requires an absolute persistent replay database. A missing guard,
storage error, UNKNOWN result, duplicate in another worker, or duplicate after
restart rejects. A legal status recheck therefore uses a fresh request ID; the
same signed authorization request is never reusable.

First claim requires an injected authenticated Owner authorization and the
authenticated developer identity fixed in the canonical development contract.
Caller-supplied owner/developer strings are not authority.
`development_identity_adapter.py` verifies an Ed25519 Owner grant bound to the
canonical contract digest and developer identity before producing the exact
shape consumed by `claim_development_writer`. ABSENT registration history is
allowed only for this verified first registration; the adapter creates no
historical event itself.

## Artifact and operational workflow

`development_authority_release.py manifest` binds the application artifact to
the reviewed commit/tree and SHA-256 with `deployment_authorized=false`.
Operators must inspect the manifest and preflight first, back up executable,
unit/config/public trust bundle and database backup manifest, apply only an
approved exact artifact, query with positive and negative probes, and recover
by restoring those backups. Key rotation publishes and probes the new public
anchor before signer cutover, retains the prior config for rollback, and removes
the old anchor only after both probes pass. These are audit requirements, not
deployment authorization; this source change performs no install or rotation.

## Rotation, recovery and compatibility

1. Generate the next Ed25519 key offline; publish its public anchor first.
2. During a bounded overlap, accept both explicitly pinned anchor IDs, but sign
   each envelope with exactly one key. Never distribute the private key to a
   reader or TEST_ONLY process.
3. Restart the issuer on the frozen artifact, probe old/new anchors, then remove
   the old public anchor and securely retire the old private key.
4. On startup, identity change, clock rollback, ledger/schema failure or signer
   failure, stop serving authorization and preserve the prior config and logs.
   Restore the database only through the ledger's documented backup process;
   re-check inode identity and registrations before restart.

Legacy HMAC envelopes and v1/v2 schemas are rejected. A staged compatibility
adapter may query an old provider for display-only status, but it must always
return `authorized=false` and cannot feed execution. Rollback removes the v3
route and restores the pinned prior service/config; it never converts v3 proof
into legacy authority.

After deployment, acceptance requires a real provider and formal task
registration: one correctly bound positive envelope must authorize, while
wrong task/attempt/lease/fence/epoch/scope/service/issuer/version, stale,
revoked, replayed and tampered envelopes must all reject. Unit tests do not
replace that wiring evidence.
