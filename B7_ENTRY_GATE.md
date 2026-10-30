# B7 exact entry gate — documentation only

B7 remains unimplemented and unrun by this candidate. It may be considered only
after B6 CP12/CP13 is **actually COMMITTED** and a fresh query proves the same
current instance and authoritative state. Source PASS, PREPARED, a historical
epoch, or a handoff receipt is not this gate.

## Required B6 output interface

The B6 completion receipt must be immutable and independently retrievable, bound
to all of the following current values:

1. task/spec and B6 artifact SHA;
2. canonical ledger UUID and DB path/identity;
3. instance, generation and epoch;
4. activation descriptor identity and journal head;
5. exact provider transition and current inflight/external-effect classification;
6. source DB/WAL custody and fresh target query digest;
7. `state=COMMITTED`, writer stopped, effects `NONE` or `KNOWN`, and verified
   authority; and
8. observation time and bounded validity window.

The fresh query must independently return the same ledger/instance/epoch,
descriptor/journal head, task/spec and target digest. Any mismatch or UNKNOWN is
`B7_HOLD_B6_FRESH_QUERY_MISMATCH`, not permission to repair or activate.

## CP14 entry

Only the original same-instance activation authority may admit CP14. Re-read the
current task/attempt, fence/lease, native execution, provider transition and
external inflight state immediately before activation. Require no old Writer and
no UNKNOWN effect. Use the current exact activation API; never replay historical
epoch 7→8 state or infer ACTIVE from source/tests.

## CP15 entry

Require CP14's immutable ACTIVE receipt and a second fresh read of the same
descriptor/journal head. Resolve the current release/config and exact original
`START_UNITS`/`BOOT_UNITS`, boot-before state, enable intent, daemon reload,
nginx test, boot enablement, service active state, gateway inspect-activate and
retained timer scope. Each action needs current authorization. Do not infer TLS
issue/renew/dry-run permission, and do not use historical unit names as current
facts.

## CP16 entry

Require the same CP14/CP15 identity and freshly active bound services. Run the
current postchecker and gateway inspect-post; verify retained certificate public
digest equals served digest and exact local HTTPS observations. Historical
predicate references (`/owner/` 200, state endpoint 401/403, callback 403/405)
are review inputs only until the current interface is verified. Model and
notification calls must remain zero unless separately authorized.

Technical CP16 does not satisfy Owner acknowledgement, business E2E, customer
acceptance, or production acceptance. Those gates remain separate exact-artifact
receipts. This file grants no install, service, root, certificate, credential,
network, or production authority.

