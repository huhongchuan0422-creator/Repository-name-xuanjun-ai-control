# Authority provider security basis (2026-11-08)

## Cryptography pin

`cryptography==42.0.8` remains exact-pinned. It is the latest 42.0.x maintenance
release, provides the Ed25519 primitives used here on the supported Python 3.11
runtime, and avoids an unreviewed major/minor API transition. Compatibility is
executable: `development_authority_runtime.py` rejects any other installed
version, while authority tests exercise PEM/raw key loading, signing, signature
verification, canonical digest validation, malformed base64 rejection, and a
wrong-key rejection path.

## Production boundaries

* A production Supervisor accepts only a `DevelopmentIdentityVerifier` instance.
  `TrustedRegistrationVerifier` binds the owner trust key at construction.
* Test injection is not a formal-provider credential. Formal provider startup
  rejects test-ledger identities independently of environment variables; test
  fixtures enter only through the isolated test constructor.
* Replay consumption is owned by the authenticated authority service, not by a
  reader/worker configuration. Its provisioned device/inode identity is fixed
  at startup and checked on every request. Consumption is one atomic SQLite primary-key insertion over issuer,
  provider instance, signed purpose, target/artifact SHA-256, and request ID. All formal workers must use
  the same formal replay ledger; inability to open/consume is `UNKNOWN`
  and fails closed.
* Recovery requires a durable operation id plus expected generation/status CAS.
  A repeated operation returns its original receipt without another transition;
  UNKNOWN is reconciled against content-addressed evidence before state changes.
* Release verification uses an exact schema and Ed25519 signature, and binds the
  artifact filename, artifact SHA-256, source SHA-256, commit, tree, and the
  literal `deployment_authorized: false`. Verification failure exits 69.

No deployment, registration, installation, or production mutation is authorized
by this document or by a verified release manifest.
