# Development authority reader v3

The endpoint `GET /api/v3/development-authority?task_id=...` reads only the
configured canonical development ledger. It does not read the Task Center
fixture database, issue authority, or mutate the ledger.

## Provider configuration

Pass `--authority-provider-config-file` with an owner-only JSON file:

```json
{
  "ledger_db": "/path/to/formal/xuanjun-ledger.sqlite3",
  "issuer": "xuanjun-ledger",
  "instance_id": "development-dispatcher-1",
  "version": "3.0.0",
  "trust_anchor_id": "development-authority-anchor-1",
  "service_id": "reader-v3",
  "bearer_token_file": "/path/to/reader-token",
  "signing_key_file": "/path/to/signing-key",
  "permissions": ["development-authority:read"]
}
```

The token and signing key files must be owner-only files accepted by
`secure_file_input`; the token is at least 16 characters and the signing key
at least 32 bytes. The formal ledger must differ from `--db`. Paths below
`/opt/xuanjun-task-center-test/current/` are rejected.

The reader sends `Authorization: Bearer ...` and
`X-Xuanjun-Service-Identity: reader-v3`, then calls
`verify_development_authority(...)` with its pinned anchor id and key. It must
also reject a payload whose `authority.fresh` is false or whose identity,
task, attempt, lease, fence, epoch, or resource scope differs from its request.

## Installation and rollback

1. Install the frozen commit and verify its Git tree before restart.
2. Provision the formal ledger path, the two owner-only secret files, and the
   owner-only provider JSON; add the CLI flag to the existing loopback service.
3. Put the reverse proxy route for this exact GET endpoint behind the same
   HTTPS host. Do not expose a mutation method.
4. Probe first without credentials (must be 403), then with the enrolled
   reader identity and verify the signed envelope and freshness.

Rollback removes the CLI flag and reverse-proxy route, restarts the prior
frozen commit, and leaves the canonical ledger untouched. Token/key rotation
is performed by replacing the owner-only files and restarting the service.
