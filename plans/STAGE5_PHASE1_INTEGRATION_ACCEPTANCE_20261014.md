# Stage5 Phase1 unified simulated integration

Authority: existing Issue #76, Stage5 approved requirement. Owner CHATGPT_NATIVE. Status IN_PROGRESS; live funds and UK deployment excluded.

## Unified work queue — one system, not disconnected ten-item batches

| ID | Module | Reuse now | Missing to reach integrated Phase1 |
|---|---|---|---|
| P1-01 | Tenant, merchant, store | PR88, PR90 merged | persisted source and ownership |
| P1-02 | Consumer storefront, catalog | PR92 merged | scoped live mock data, real browser E2E |
| P1-03 | Signed QR scan and amount | PR88 merged | end-to-end browser/server QR validation |
| P1-04 | WeChat mini-program shell | route contract merged | executable test pages (no public release) |
| P1-05 | Official-account H5 shell | route contract merged | executable H5 test pages |
| P1-06 | Persistent simulated order state | PR91 merged | unified local API and strict identity |
| P1-07 | Local simulated HTTP API | PR94 Draft | independent review and integrated tests |
| P1-08 | Consumer-to-API client | PR95 Draft | response repair audit; real click wiring |
| P1-09 | Merchant order/advert console | PR93 merged | shared mock backend scoped data |
| P1-10 | Platform approval console | PR93 merged | server-side role checks and stored approvals |
| P1-11 | Two ads/moderation/fallback | PR73/75/92 merged | actual approved selection and resilience |
| P1-12 | Split/refund/reconciliation preview | PR88/89 merged | persistent adjustment event chain |
| P1-13 | Full local simulated E2E | partial sources above | scan→amount/ad→order→pending→simulation→result/ad→merchant report |
| P1-14 | Security and recovery | separated tests | authorization, data boundary, fault injection, restore |
| P1-15 | Single reproducible project | scattered workflows | local runbook and aggregate exact-head CI |

## Non-negotiable gates

PHASE1_ACCEPTANCE=NO until all 15 items are integrated into a usable simulated system, verified on one database/source of truth through consumer and both admin interfaces, with cross-tenant negative tests, refund/advert invariants and browser E2E.

PR94/95 remain independent Draft until reviewed. Browser/user-supplied identity and simulation booleans do not authenticate money. No wildcard CORS to bypass loopback boundaries. Provider settlement verified must stay false in simulated calls. Ads cannot modify payment or beneficiary. No live WeChat payment, UK install, domain changes, credentials, P2 or Work17 source ownership changes.

Continue under existing Issue #76 without creating a duplicate issue queue. All CI PASS means only tested scope, not Phase1 or production release.
