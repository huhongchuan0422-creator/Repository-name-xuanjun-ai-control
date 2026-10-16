# PR122 backend migration increment — offline conversion and isolated runtime

This continues S04/S05/S06; it is not another OAuth implementation or permission
to activate production. The seven reviewed OAuth modules stay byte-identical to
the approved d584cd60 candidate and its 7-file manifest. No original 45 tests are
rerun. Work website content/current, DNS, Nginx and Tokyo services are untouched.

## Implemented in this increment

`custody.normalise` validates an in-memory, private operations-only snapshot.
It preserves session IDs, customer/account identities, CSRF hashes/nonces,
expiry, attempt counters, used forms and idempotency; client credential pairs,
token pairs and lifecycle stay together. OAuth state hashes, expiry and consumed
timestamps are preserved in the corresponding provider SQLite store. An already
consumed state cannot become reusable after conversion/restart.

Trading SecretRefs, mixed/trading sessions, partial credentials, wrong origins,
wrong provider/client/account bindings and unsupported scopes are rejected before
creating a target. Multi-form legacy sessions also require a separate renderer
successor; they are rejected rather than silently dropped or made inaccessible.

Legacy masked IDs cannot establish exact account identity. An active token
requires an independently established exact account hash from the trusted
private fence context AND an explicitly supplied private provider verification
adapter bound to that access token. `PrivateIdentityVerifier` now wraps the
reviewed clients' user-info interfaces, but creates no clients automatically.
It requires exact private account anchors and explicitly admitted clients;
this increment uses only fake clients. Missing proof fails before target writes. Revoked, disconnected or
expired state remains inactive and retained, without pretending it is connected.

`prepare_generation` writes only a new caller-owned 0700 offline generation,
using the existing FULL-synchronous SQLite stores. READY is written last after
all three stores and the private receipt. There is no current-pointer update,
service action, production path default, transfer, source mutation or automatic
cleanup. A partial failure leaves the generation unready and preserves evidence;
the same target refuses retries. Cross-process creation has one winner.

`isolated_runtime.make_isolated_server` runs on loopback with provider calls
disabled. It requires a private regular READY marker and no failure marker.
The standby wrapper permits only GET /healthz, refuses other GET/POST with503,
and preserves the accepted temporary TikTok disconnect denial: fixed403,
operation_performed=false, before request-body or credential-store access. It does
not add login or authenticated disconnect. Tests use temporary state and fake
identity verification; they never read production state or call a provider.
In particular, /p/douyin cannot create a new OAuth state in standby.

`private_source` is a bounded private reader library, not a privileged entry
point. Its default fixed-host guard requires root on Tokyo, inactive/dead
Portal with MainPID0, refused loopback18080 and the exact R4 source bytes. It
does not stop the service. Selected sessions and the eight OAuth SecretRefs
are read through checked directory descriptors, with strict owner/mode,
non-symlink regular-file identity, JSON, size and before/after generation checks.
Metadata value_path is never used as a read target. Values remain in memory;
the reader neither prints nor transfers them. Custom roots and fake guards are
synthetic test seams, not inputs to any installed root capability.

The reader's returned fence deliberately says writer_fenced=false. A stopped
Portal proves neither exclusive custody nor the absence of other writers;
normalise rejects this partial fence until a separately approved orchestrator
establishes the complete writer scope. Do not turn that flag on without proof.

## Trust and incomplete production integration — explicit blockers

The fence argument is supplied by a trusted caller outside the input snapshot;
validating its fields is NOT proof that the old writer actually stopped. This
library does not cryptographically authenticate a snapshot or perform root
admission. Before live use, the accepted I1/Owner-root admission pattern must
bind the exact new adapter, independent action approval, source/target identities,
snapshot generation, actual writer drain/fence and protected transport. No live
transport, root installer, production unit or automatic activation is provided
here. Do not run this reader against real data or wire it into a live Runner.

Private reader and identity interfaces have been implemented, but neither has
been executed against production data. Protected transport and full writer
custody/root admission remain unimplemented. Do not report S05 complete
or treat passing synthetic conversion tests as a production migration permit.
No secrets, database snapshots, environment files or business exports belong in
GitHub/chat/CI artifacts. Real data must stay within an explicitly reviewed
protected host-to-host channel. Historical audits remain privately retained at
their existing authority; this code does not export audit history.

Tokyo18080 still serves non-OAuth credentials and Telegram; these successors,
legacy mixed sessions and their protected authority are separate remaining work.
Keep Tokyo and all bridges/callbacks running. PR99 owns trading/Finance migration.

## Verification

Run only the new group:

    python3 -B -m unittest discover -s tests -p 'test_pr122_backend_*.py' -v

It covers exact state continuity, rejection without writes, process competition,
hard exit and partial-commit preservation, inactive-account preservation, and a
real temporary loopback HTTP adapter. Source tests are separate from the actual
nonroot host-metadata preflight and from any future root/private-data execution.
