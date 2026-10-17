# PR122 remote custody evidence: offline increment

The Owner authorized GitHub Actions → STS → SWAS execution, but that transport
authorization does not waive independent review, custody proof or Release Gate.
The blocked r2 permit remains unissued. No old permit may be reused.

This increment provides only a side-effect-free Ed25519 envelope validator.
It does not replace or invoke the approved TTY launcher, prepare, upgrader,
rollback or installer. It has no machine or network entry point.

The caller must obtain its trust registration from separately reviewed,
Owner-protected storage, never the repository/request. Registration binds the
Owner signing key, writer/reviewer principals, purpose, expiration, revocation
and evidence hash. A developer-generated fixture key is never a production key.
The signed payload binds the domestic host, attempt, exact commit, launcher,
review ZIP and complete audit body hash. Exact schemas reject extra permissions.
Signature validity does not prove actual independence or grant execution.

Next integration must verify protected trust provenance and actual evidence,
atomically consume a fresh permit bound to this different remote operation,
record the SWAS InvokeId before polling, never blindly resubmit unknown calls,
keep private evidence on the host, and publish only redacted status. Neither
that integration nor production trust registration is implemented here.
Missing genuine evidence remains HOLD; no automatic fabrication or TTY emulation.

Local validation: 8 unittest methods passed, including binding, signature,
author self-review, expiry, revoked/disabled trust, schema and redacted errors.
Hosted result must be obtained for the exact commit; no server action performed.
