# R4: temporary containment for a reduced website-migration scope

Owner asks who is responsible and how soon the website can migrate. This PR122
developer retains responsibility; no transfer to OpenClaw or new queue occurs.

## Decision requested, not assumed

Independent finding PR122#6205227893 requires a fully authenticated disconnect:
verified identity, target-account authorization, CSRF/Origin controls and durable
replay/concurrency/failure semantics. The real legacy server has no reusable
authenticated disconnect session adapter. The approved OAuth candidate is
offline and is not a production login authority; credential-submission sessions
are not login sessions or account-ownership proofs.

This smaller candidate **disables HTTP disconnect for every caller**. It asks
the independent reviewer to decide whether a website migration that explicitly
excludes this write capability can proceed after its remaining gates close.
It does not satisfy or claim the full authenticated-disconnect implementation.
AUTHENTICATED_DISCONNECT=NOT_IMPLEMENTED. R4_FULL_REMEDIATION=OPEN.
CONTAINMENT_SCOPE_ACCEPTANCE=PENDING. DNS_RELEASE=HOLD.

## Exact implementation

The pure builder accepts only deployed source SHA256
`d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0`.
It replaces only the known disconnect branch. All requests to that branch
produce403/DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED, before reading a body,
constructing a lifecycle store, changing a binding/Token or writing a business
audit event. A fixed security denial event is written to the existing stderr
stream without caller data, secrets, account identifiers or arbitrary headers.
Successful authorized disconnection is intentionally unavailable in this scope.
Other do_POST branches, GET, HEAD/log_message, Telegram and website bytes are
preserved by exact-byte replacement; no approved OAuth or312efdd3 config changes.

## Evidence and boundary

18 tests use actual deployed source bytes and extract only do_POST AST. Fake
stores/audit/response replace production dependencies. Cover original unsafe
branch, no login, supplied login still disabled, wrong target, missing/bad CSRF,
forged Origin/proxy headers, duplicate/concurrent denials, unreachable store
failure seam, query/body/header redaction, exact source hash and byte protection,
and a real ephemeral loopback HTTP403 exchange. Denials never construct a store
or write business audit; only the constant security event changes the test log.
Concurrent tests cover denied operations, not successful disconnect transactions.

No production app imports, real credentials, provider calls, real POST, source
installation, restart, root grant extension or DNS change occur in this round.
The existing root helper permits only its spent original log-fix action; it
cannot deploy this different candidate. Production containment still needs an
appropriately registered and reviewed execution action after scope approval.
Long-term Owner authorization remains in force; capability limits are technical.

Full disconnect restoration remains separately gated on a real authenticated
identity/account-ownership adapter and the review's positive/negative/concurrent
failure tests. This candidate must not be renamed to imply that gate is closed.
