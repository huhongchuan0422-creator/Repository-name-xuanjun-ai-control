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
* Test injection requires both the explicit `TestOnlyDevelopmentIdentityVerifier`
  type and `XUANJUN_TEST_ONLY_IDENTITY=1`; a lambda supplied directly is rejected.
* Replay consumption is one atomic SQLite primary-key insertion over issuer,
  provider instance, signed purpose, target/artifact SHA-256, and request ID. All formal workers must use
  the same absolute replay-ledger path; inability to open/consume is `UNKNOWN`
  and fails closed.
* Release verification uses an exact schema and Ed25519 signature, and binds the
  artifact filename, artifact SHA-256, source SHA-256, commit, tree, and the
  literal `deployment_authorized: false`. Verification failure exits 69.

No deployment, registration, installation, or production mutation is authorized
by this document or by a verified release manifest.
