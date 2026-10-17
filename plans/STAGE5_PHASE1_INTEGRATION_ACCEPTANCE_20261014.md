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

## 2026-10-14 continued business implementation checkpoint — PR118 DRAFT, NOT MERGED

This later checkpoint supersedes earlier historical PR-state wording **for development status only**. It does not overwrite earlier independent-review evidence or authorize production.

| Item | Implemented local simulated capability in PR118 or merged main | Unresolved external / acceptance limit |
|---|---|---|
| P1-01 | Local merchant/platform capability secrets are owner-provisioned via environment, bound server-side to role/scope; negative HTTP and Chromium tests | Not real customer, WeChat or provider identity; production RBAC / session revocation absent |
| P1-02 | SQLite merchant and catalog rendered in consumer and management Chromium via scoped localhost HTTP | Merchant onboarding and real account provisioning absent |
| P1-03 | Server-keyed short-lived signed QR create/verify plus QR-validated PENDING order in actual Chromium | Demonstration QR issuance is not authority over live merchant payment |
| P1-04 | Executable local mini-style shell and real browser QR-to-order path | Not compiled/published native WeChat Mini Program |
| P1-05 | Executable local official H5-style shell and real browser QR-to-order path | Not deployed through verified WeChat Official Account OAuth |
| P1-06 | SQLite order, append-only simulated event and restart persistence regression | Provider transaction events/callbacks absent |
| P1-07 | Loopback exact-route HTTP with body/header absolute deadline, fail-closed JSON/Origin/Host protections | Not a public service |
| P1-08 | Consumer HTML/JS real Chromium storefront, order and simulation result | Does not execute payment |
| P1-09 | Merchant local page: scoped orders, catalog, ads, order metrics, refund previews, capability-gated edit | Not real merchant customer portal |
| P1-10 | Platform local page: scoped read, creative review, campaign states, reconciliation preview, role token tests | Not real production staff IAM |
| P1-11 | Both ad slots persisted, moderation/activation flow; AMOUNT active creative rendered; SUCCESS hidden without provider proof | Real receipt advertising requires verified provider event |
| P1-12 | Offline append-only refund previews, no-refund effect, simulated split conservation and reconciliation reporting actual provider settlement UNKNOWN | Real split/refund/clearing excluded and must not be marked zero |
| P1-13 | Actual Chromium: signed QR -> consumer storefront+approved ad -> PENDING SQLite order -> merchant & platform read with scope isolation | Only local simulation |
| P1-14 | Cross-scope denial, role-bound admin, malformed/slow HTTP, tampered QR, reset/SQLite durable restart and append-only invariants | Operational production disaster recovery/real auth not performed |
| P1-15 | Single PR118 incremental branch, full community+Stage5+JS+real Chromium on GitHub hosted exact PR HEAD | Final independent integrated review and merged-main acceptance not yet performed |

**Actual development evidence at pre-checkpoint HEAD bf695fccdd51a7e6cab15392da42cf9a43ff6804:**
Stage5 Full Local Integration Gate run 38594543490 / job 115957745804: SUCCESS, exact checkout, community Python 144/144, Stage5 Python 67/67, five JavaScript groups 14+4+4+8+7 all PASS, separately repeated original Chromium 4 PASS. Stage5 Current Main Source Gate run 38594543459 / job 115957747545: SUCCESS, same exact HEAD and tests. Integrated restart, signed QR and end-to-end management browser tests actually executed and passed.

**Scope markers (never infer from CI labels):**
- PHASE1_LOCAL_SIMULATION_SOURCE_CANDIDATE=YES
- PHASE1_INDEPENDENT_INTEGRATED_REVIEW=PENDING
- PHASE1_ACCEPTANCE=NO
- REAL_WECHAT_MINI_PROGRAM=NOT_DEPLOYED
- REAL_WECHAT_OFFICIAL_H5=NOT_DEPLOYED
- REAL_PAYMENT_PROVIDER_SETTLEMENT=NOT_CONNECTED
- REAL_REFUND_AND_SPLIT=NOT_EXECUTED
- PRODUCTION_DEPLOYMENT=NO
- UK_P2_RELEASE=HOLD

PR118 is a development candidate. No merge, host access, real payment, merchant funds, approval or owner P2 grant is implied.
