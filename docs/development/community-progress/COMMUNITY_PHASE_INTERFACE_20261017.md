# Community Phase 1/2: Original Center API handoff (2026-10-17)

Status: IN_DEVELOPMENT. This is code/interface evidence, not production authorization, live payment acceptance, full phase signoff or a commercial price.

## Canonical boundaries
Mini customers are authenticated using the original CenterIdentity, signed mini session and protected scene. Project authority, member roles, tenant, customer ID, encrypted materials, transitions and feedback remain in the pinned original Center Core/Source/Runtime. No second IAM, CRM or Finance ledger. Money operations remain gated.

## Mini commerce operations (all POST /mini/api, operation prefixed commerce.)
| Operation | Params | Source-backed behavior |
| --- | --- | --- |
| receipt_ad | reference | Checks same user owns original basket, original paid SUCCESS order and signed provider evidence before optional success creative; finance_status always UNCONFIRMED. Never honors a client-supplied paid boolean. |
| project_summary | empty object | Original Center project title, member role, project CRM customer ID, requirement revision and checklist overall. |
| project_checklist | empty object | Original Center checklist and versioned requirement states, including original internal-material filtering. |
| project_feedback | message | Original Center encrypted WEB message archival; ARCHIVED does not mean answered. |
| project_messages | empty object | Reads original Center bounded archived project conversation after current project authorization. Message ARCHIVED and provider_reply_verified=false must not be presented as answered. |
| project_submit | item, revision | Existing original requirement revision is submitted via original Center.transition(... submit). No reviewer approval or material minting. |
| project_review (web only, /community/commerce) | workspace = original project ID; params: item, revision, action, reason | Only original Center web session + CSRF and original project REVIEWER can begin_review / request_changes / approve. Mini bearer sessions cannot invoke this operation. Original material author/reviewer separation and revision/category/expiry guards are mandatory. |

## Client behavior
Native mini checkout displays success creative only on original server-confirmed signed successful payment evidence; a synthetic SUCCESS order retains MOCK_PAID_SIMULATED status without success creative. Ads are optional and failures do not block payment querying. Existing amount slot cannot forge success.

## SaaS registration
original_project_center and verified_receipt_ad are metadata-only general modules with existing dependencies; no implicit prices, discounts, entitlements, third-party agency fees or releases. Existing itemized dual-currency quote and approval remain authoritative.

## Synthetic tests (not live transactions)
tests/test_community_refund_execution_recovery.py; tests/test_community_provider_terminal_binding.py; tests/test_community_owned_receipt_ad.py; tests/test_community_original_project_center.py; tests/test_community_stage_runtime.py; tests/test_community_mini_runtime_e2e.py; tests/test_community_stage_browser.py; clients/community-mini/session.test.cjs; tests/test_community_module_catalog.py; tests/test_stage5_saas_modules.py.

Hosted CI requires actual exact-commit test job SUCCESS. Optional mini runtime, SDK and preview SKIPPED means NOT TESTED, not PASS. Independent phase audit has not happened.

## External or unresolved
Real submerchant and WeChat approval, official split receiver-level bill format, production CRM admission, authoritative original Finance reconciliation, production mini-program publish and actual payment/refund remain BLOCKED or UNKNOWN. Unknown provider layouts stay UNKNOWN_SCHEMA; settlement stays UNCONFIRMED.

## Scoped provider-bill reconciliation audit (candidate)

The original finance-authorized `/community/provider-actions` supports `bill_audit` with `{kind, bill_date, after_id}` after an already ingested signed-ticket/hash-verified bill. It reads only existing original encrypted Center reconciliation records for that project and exact merchant/store scope; returns at most 50 immutable result snapshots and a cursor. It checks each audit row against the existing SHA256 event key and returns `finance_status=UNCONFIRMED`. Historical snapshots lacking original scope metadata are not implicitly trusted or shown. No new money ledger, payout or issuer role.
