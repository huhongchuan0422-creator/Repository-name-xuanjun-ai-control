# Development checkpoint — source work remains open

This file preserves a recoverable development state, not phase acceptance.

## Current repository

Original branch: `feature/chatgpt-community-wechat-sp-offline-20261017`.
Latest published source before this checkpoint: `dc2e7ba9e93e580613ffb28fe6063afc30c264d3` (platform lifecycle); official bill source: `0424f69f6d1b4e1b0394188463f2f7737624126e`. Signed payment-time evidence and reverse daily reconciliation accompany this checkpoint commit.
Original customer Core/Source/Runtime pinned bytes have not been changed. Business extensions use encrypted records in the original Center links/events/audit domain, not new IAM or Finance databases.

## Actual new source integrations

- Provider refund/split actions, verified order projection, durable operation reservations and unknown-result query recovery.
- Original SaaS fulfillment and reversal with separately trusted Finance authority receipt verification; actual Finance issuer admission remains external.
- Community registration, revisioned profile edits, independent review, correction/rejection/approval/pause and explicit customer/merchant membership.
- Customer profiles, original project CRM customer ID reads, immutable opt-in referral binding with cycle prevention, private in-app notices.
- Immutable split-rule versions, original largest-remainder calculation, policy limits, per-order snapshots automatically frozen before profit-sharing prepay.
- Server-priced basket orders, product price/inventory revisions, original customer ownership, immutable line/community/referrer snapshots and same-reference cross-store recovery.
- Raw payment callback RSA verification, AES-GCM decryption, immutable original-order binding, actual order projection and callback idempotency.
- Consumer refund application, independent merchant decision, protected finance execution and original-request query recovery.
- Official merchant-receiver split returns, bounded cumulative reservations, signed result/query binding and refund impact guards. Personal receiver returns are unsupported by the official API and held explicitly.
- Store staff invitations reuse original Center invitation acceptance; store read permissions are separately delegated to existing registered staff principals and revoked without broad project revocation.
- Scoped payment/refund/split-return observations, financial pages and signed per-order reconciliation snapshots/history. These do not attest official daily-bill reconciliation or Finance settlement.
- Workbench, community portal and native checkout connect to these APIs under existing authentication boundaries.

## Honest remaining source work

Neither phase is complete. In particular, the following cannot be marked implemented merely because nearby code exists:

1. Official submerchant application transport, private drafts, common domestic identity/bank form, scanned-material media upload, separate internal review, gated submission and signed status synchronization have now been written. Remaining: complete conditional administrator/foreign-identity/beneficial-owner/industry/bank-branch form requirements and final integration. Existing platform merchant onboarding remains separate.
2. Original CRM-admitted multi-store business profiles, merchant fulfillment completion and platform ACTIVE/PAUSED/DISABLED lifecycle are implemented. New trading is blocked when suspended; existing status/cancellation/refund recovery remains available. Creating new CRM identities still belongs to original admission authority.
3. Native personal center, immutable referrals, private notices, original-owned order history, signed payment close and exactly-once stock release are implemented. Final four-role frontend coverage remains development work.
4. Raw refund callbacks and hash-verified official bill downloading/private ingestion/scoped reconciliation are implemented. Reverse trade reconciliation uses signed payment dates; undated legacy payments are explicit partial coverage. Unsupported receiver-detail split bill schemas remain UNKNOWN and require a verified official format adapter; current aggregate adapter must not be claimed as complete official split-bill support. Finance核销 is separate and requires original admitted authority.
5. Community attributed order and signed payout/return views, immutable receiver/community rule snapshots, platform admitted-merchant overview and lifecycle are implemented. Broader community/customer operational views and promotion records remain source work.
6. Final frontend integration and source security review, meaningful tests for remaining newly written paths, complete regressions/E2E, actual current-source CI and concentrated independent phase reviews remain outstanding.
7. Update original issue/PR acceptance records only after real source evidence and final CI exist.

## Supervision

PR #125 (supervision only) merged into protected `main` as `8734b82d40ebb9335d47f837144b41237c2badbf` after the required feature-compliance gate passed. Schedule is every ten minutes; first scheduled execution was verified at 2026-10-17T09:36:44Z (remote board commit bfccf102f2ef4448ee3df2950234a6edd48d62c7). The watcher reads actual code commits, excludes board/document changes, and marks source inactivity after twenty minutes. Schedule delays are possible. It does not keep an AI coding session running.

## Validation and external dependencies

Latest Owner instructions allow iterative testing. Source `a9f5aa275fffe2a6291285e45a8e2398b8761151` has actual hosted CI PASS: run 39022398009, job 117366639653, 382 community Python + 342 stage5 Python + 81 JavaScript executions. This receipt does not cover subsequent store/community report/bill/lifecycle changes. Those have targeted new tests (stores 3, reports 2, bills 8, lifecycle 3), plus affected payment/refund/cancellation tests; final current-source CI must still be checked. Optional domestic runtime/SDK/preview jobs were skipped in that passing run and are not attested.

No real merchant onboarding submission, funds operation, deployment, new key generation or production IAM mutation has been performed. Real submerchant and production admission remain external dependencies. Source development gaps above remain development work, not external blockers.


## 2026-10-17 controlled handoff continuation — refund-provider recovery

- Exact source branch: `feature/chatgpt-community-wechat-sp-offline-20261017`. No Work/Codex calls. No production deployment, live funds, special merchant enrollment or extra ledger.
- Refund application execution: same approved application can recover a consumed reservation with no ProviderAction intent; the explicit query path cannot initiate a POST. Existing durable ProviderAction intent is queried only. Terminal application statuses cannot flip or increment revision on same result.
- Provider response validation: signed refund response must bind to original transaction ID, and FINISHED receiver results cannot be rewritten on later queries.
- Added synthetic focused regressions: `tests/test_community_refund_execution_recovery.py` and `tests/test_community_provider_terminal_binding.py`.
- Previous source HEAD `1364ac47f587778c6fb67f0e670003038b57c81e` has GitHub Hosted test SUCCESS (run `39024446841`); mini-SDK/runtime/preview checks SKIPPED, not PASS.
- Subsequent regression test run `39024920270` failed 1/419 due to an inaccurate test-double query for nonexistent provider intent, not a verified production provider failure. The double was corrected in `67372f3e8ee03669cf616bfa5e11818a54f3c7ef`. Current exact regression CI must still be checked at its latest commit before PASS can be stated.
- Other first/second-phase groups remain PARTIAL. Original three-file customer Core/Source/Runtime pins remain unchanged. External merchant approval, real WeChat transactions, authoritative Finance settlement and live mini-program release remain gated.
