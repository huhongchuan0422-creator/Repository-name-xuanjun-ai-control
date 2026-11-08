# Development authority provider/reader v3

`development_authority_provider.py` is the formal loopback issuer. The
TEST_ONLY Task Center application neither exposes this route nor loads a formal
private key. Consumers receive only the pinned Ed25519 public key and must call
`verify_envelope` with values from trusted configuration and the actual request;
no expected value may be copied from the envelope being verified.

## Frozen installation

Install an exact reviewed commit and tree (never a moving branch or `latest`),
record `git rev-parse HEAD HEAD^{tree}`, and pin the Python wheel/application
artifact by SHA-256. Before replacing anything, copy the prior executable,
service file, owner-only configuration, public trust bundle, and database backup
manifest to a dated owner-only rollback directory. Do not copy the private key.

The issuer configuration has exactly these fields:

```json
{
  "ledger_db": "/srv/xuanjun/formal/development.sqlite3",
  "forbidden_ledger_paths": ["/srv/xuanjun/test/task-center.sqlite3"],
  "issuer": "xuanjun-formal-ledger",
  "instance_id": "development-authority-01",
  "version": "3.0.1",
  "anchor_id": "development-authority-2026-11",
  "service_id": "mcp-authority-reader",
  "bearer_token_file": "/etc/xuanjun/authority-reader.token",
  "private_key_file": "/etc/xuanjun/authority-ed25519.pem"
}
```

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

First claim requires an injected authenticated Owner authorization and the
authenticated developer identity fixed in the canonical development contract.
Caller-supplied owner/developer strings are not authority.

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
