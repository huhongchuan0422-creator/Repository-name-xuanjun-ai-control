# Stage5 Phase1 unified simulated integration

Authority: existing Issue #76, Stage5 approved requirement. Owner CHATGPT_NATIVE. Status IN_PROGRESS; live funds and UK deployment excluded.

## Unified work queue — one system, not disconnected ten-item batches

| ID | Module | Reuse now | Missing to reach integrated Phase1 |
|---|---|---|---|
| P1-01 | Tenant, merchant, store | PR88/90/97 merged | trusted owner session/auth and merchant-bound API |
| P1-02 | Consumer storefront, catalog | PR92/98/100/102 merged; PR105 browser source approved, Draft | scoped persisted catalog and ads still not wired to browser HTTP |
| P1-03 | Signed QR scan and amount | PR88 merged | end-to-end browser/server QR validation |
| P1-04 | WeChat mini-program shell | route contract merged | executable test pages (no public release) |
| P1-05 | Official-account H5 shell | route contract merged | executable H5 test pages |
| P1-06 | Persistent simulated order state | PR91 merged | shared local API is PR94 Draft, identity remains self-asserted |
| P1-07 | Local simulated HTTP API | PR94 Draft | independent review and integrated tests |
| P1-08 | Consumer-to-API client | PR95 merged; PR101 source-review passed, Draft | retain PR105 UUID fix, upstream integration, authenticated identity |
| P1-09 | Merchant order/advert console | PR93 merged; PR103 source-review passed, Draft | local read-only order HTTP linked; merchant/ad writes and session ACL not linked |
| P1-10 | Platform approval console | PR93 merged; PR104 source-review passed, Draft | local read-only order HTTP linked; moderation API/RBAC not linked |
| P1-11 | Two ads/moderation/fallback | PR73/75/92/98/100 merged | validated SQLite selection exists, but no real browser-backed ad HTTP placement |
| P1-12 | Split/refund/reconciliation preview | PR88/89 merged | persistent adjustment event chain |
| P1-13 | Full local simulated E2E | PR105 actual Chromium 4/4 source-reviewed, Draft | QR->persisted storefront/ad->order->truthful receipt->two admin views still incomplete |
| P1-14 | Security and recovery | separated tests | authorization, data boundary, fault injection, restore |
| P1-15 | Single reproducible project | PR106 aggregate 154/154 green, Draft, audit pending | merge stack, retest main HEAD and document recovery |

## Non-negotiable gates

PHASE1_ACCEPTANCE=NO until all 15 items are integrated into a usable simulated system, verified on one database/source of truth through consumer and both admin interfaces, with cross-tenant negative tests, refund/advert invariants and browser E2E.

PR94 and PR96 await independent review; PR101/103/104/105 source-reviewed with strict stacked dependency; PR106 aggregate integration gate awaiting independent review. PR95 has already merged. Historical CI on old pull/merge preview does not substitute for final main HEAD testing. Browser/user-supplied identity and simulation booleans do not authenticate money. No wildcard CORS to bypass loopback boundaries. Provider settlement verified must stay false in simulated calls. Ads cannot modify payment or beneficiary. No live WeChat payment, UK install, domain changes, credentials, P2 or Work17 source ownership changes.

Continue under existing Issue #76 without creating a duplicate issue queue. All CI PASS means only tested scope, not Phase1 or production release.

## 2026-10-14 reconciled source checkpoint (not a change to acceptance)

Current stack order: PR94 -> PR101 -> PR103 -> PR104 -> PR105 -> PR106. PR94 and this PR96 still require independent review; no release permitted. PR105 alone fixes the prior per-page simulated event/transaction ID collision using browser crypto.randomUUID; never deploy the older PR101-only source as a complete UI. PR106 runs Stage5 Python, JavaScript and Chromium against one exact stacked head, but does not prove a verified payment, role-based access, merchant/ad HTTP source, unified DB atomicity or production availability. All PR numbers above are historical snapshot references; before merge inspect latest GitHub state again. **PHASE1_ACCEPTANCE=NO.**
