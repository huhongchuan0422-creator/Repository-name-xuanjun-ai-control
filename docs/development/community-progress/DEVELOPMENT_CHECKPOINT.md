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


## Continued integration delta — original Center project and signed receipt-ad (2026-10-17)

- Latest source development includes `scripts/community_commerce.py` consumer operations `receipt_ad`, `project_summary`, `project_checklist`, `project_feedback` and `project_submit`. They require existing mini session/scene and original project/ownership; material submission delegates to unchanged `Center.transition(..., "submit")` with exact revision, not an independent reviewer or a second IAM.
- Mini `session.js`, checkout page JS and WXML now provide read-only signed paid-success creative, project checklist and archived feedback, and explicitly authorized material submission. A simulated success cannot display an official success-placement advertisement. Payment/Finance state remains separate; ad failures cannot block payment reads.
- SaaS original module registry now has two additional metadata-only reusable modules (`original_project_center`, `verified_receipt_ad`); no new price, entitlements or production release. Existing module-market tests updated from 20 to 22 catalog entries. Dependencies bind original modules.
- Synthetic regression coverage includes `tests/test_community_owned_receipt_ad.py`, `tests/test_community_original_project_center.py`, updated StageRuntime, mini HTTP/browser, JS session and module catalog tests.
- Actual Hosted run `39025930706` for commit `df2fbf9b0f1aab6dd6b9548528f199e027a4ed5d` succeeded for source suite after simulation-ad browser fix; optional SDK/runtime/preview checks were SKIPPED. A later run `39026032313` failed only the obsolete fixed-count assertion (22 versus 20), corrected in `a30acdde7aa115c611508c54f19274a8ed092410`; do not mark latest HEAD CI PASS until checked.
- Both stage groups still PARTIAL; original pinned Center Core/Source/Runtime are unchanged; real submerchant, live transactions, authoritative Finance settlement, production admission, public mini release and independent audit remain open.


## 2026-10-17 native handoff checkpoint — original independent materials acceptance

- Original Center consumer mini read paths and role-bound operations now include project_summary, project_checklist, project_feedback (archived only), project_submit (requires original submitted material version) and project_review (only original REVIEWER, actions begin_review/request_changes/approve, original Center independent approval + CAS).
- Mini WXML project page has submission and reviewer/correction controls; client session allowlist only forwards existing auth token, never grants roles.
- New synthetic test in tests/test_community_original_project_center.py imports an authority-signed synthetic requirement into original Center, persists synthetic SECRETREF through original save, submits via mini, and exercises separate reviewer acceptance, replay rejection. No live customer secret or project enrollment.
- Provider verified SUCCESS creative remains read-only and separate from original mocked payment success. Node checkout UI verification test was repaired for a Node vm cross-realm object equality artifact in commit 09848ffb71119414617444c1600322c17a4747f1.
- Source regression checkpoint 382955aefa3fd1ff877ff884e56fdb1c6e298922 had Hosted SUCCESS in run 39026316013 (community 431/431, stage 342/342, Node suites PASS; optional mini runtime/SDK/preview SKIPPED). Later source commits need exact fresh CI verification and are NOT marked accepted.
- Current resumed source code is on feature/chatgpt-community-wechat-sp-offline-20261017. Work/Codex not used. Pinned original customer Core/Source/Runtime were not touched in resumed commit comparison.
- Phases 1 and 2 continue PARTIAL; provider receiver-detail bill formats, legitimate public/CRM admission, browser/device coverage, authoritative Finance, real merchant/real money and independent stage approvals remain open.


## 2026-10-17 reviewer boundary correction — keep mini customer-only

- Hosted run 39026794773 discovered a real reviewer admission mismatch: original CenterIdentity mini _resolve admits OWNER/EDITOR only. REVIEWER cannot use mini credentials, by design; weakening that shared grant was rejected.
- Corrected source at a7f9d682c9f43ea6db4583d48d037f905f199694: original commerce web /community/commerce action project_review is reachable only with original Center web session, exact CSRF, valid project ID, original Center project REVIEWER membership and exact revision/action fields; business role flags from client are not accepted. Original Center.transition still enforces separate material author and reviewer.
- Removed inaccessible mini reviewer operation/UI; mini retains only original customer project_summary/project_checklist/project_feedback/project_submit. WXML closure and Node allowlist revised. This is a permission-preserving correction, not a route workaround.
- Synthetic positive integration test now creates authority-signed original Center requirement, host-verified synthetic SECRETREF, submits through mini as original owner, then reviews/approves via second original Center authenticated web session and CSRF; false/replayed approvals denied.
- Source version 39dcd47040ab0a520452b282192fdffdb80359d8 and subsequent reviewer endpoint docs/Node tests require latest Hosted CI. Do not reuse earlier SUCCESS as PASS for these new revisions.
- No real customer secret, merchant admission, Finance settlement, paid order, independent phase audit or deployment was performed.

## 2026-10-17 split-bill identifier guard (ChatGPT development)

- Development account: huhongchuan0422-creator; Dots independent reviewer account 18598789888 was not used.
- Source commits: bbf9576b59b4fdf66257e5c91cdc60efbdc05280 (verify any optional split bill submerchant and payment transaction identifiers against original signed ProviderActions intent), 39aa89798a93ce45bd8e651ed4e7cffc86a6441a (synthetic positive and wrong-merchant/wrong-transaction regression).
- Unknown receiver-detail official layouts continue to be UNKNOWN_SCHEMA, not coerced into financial matches. No automatic Finance confirmation and no live money call.
- Actual Hosted CI for new source version must be resolved before PASS; review run https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39030004104. Older passing runs do not prove these changes.
- Both phases remain PARTIAL; next work includes official receiver-detail format with authoritative documentation, merchant admission conditions, public consumer/CRM admission, broader cross-role E2E and audit.

- Follow-up safety commits 7e929d5ccf2eb83c723b30adf4a8bf8e27a52be6 and 88ba947ed958315fc576a441f9029a1cace73963 now reject even BLANK supplied split transaction/submerchant columns and add regressions. Latest exact source test run 39030062012; status must be independently fetched, no PASS claimed at writing. Phase large groups remain PARTIAL.

## 2026-10-17 conditional merchant-application hardening

- UBO identity documents in existing original merchant WeChat applyment are now deduplicated within the same application: 75f1f868dfee6796b671530513ae8ff3d3cbcc4e. Multiple records with the same (document type, case-normalized document number) are rejected before upload/submit; never print the document number in error text.
- Synthetic regression added in 51ebb6ce72541dcf55d1f9cf814912f6ebff9d5f. No real merchant enrollment performed. Real bank and sector dynamic catalogs remain unverified/external; this test is not live merchant acceptance.
- CI for this new source version must be checked by exact SHA; prior success for split-bill improvements is not a PASS for applyment.

- Official WeChat partner split-bill API documentation (https://pay.wechatpay.cn/doc/v3/partner/4012761140) says each detail row is an individual split or return and that detail/summary each have their own header. The current aggregate-only adapter is NOT validated for official receiver-level/return layouts: UNKNOWN_SCHEMA remains mandatory. Do not label current synthetic aggregate fixtures as full official reconciliation or Finance settlement.
- Verified latest source CI: cf01f58e9acefa98f34e1711c963ea9d80c2cbe3, Hosted run 39030394638 test job 117389505111 SUCCESS; optional jobs SKIPPED, not PASS.

## 2026-10-17 later split/trade bill parser hardening

- Receiver-detail variants containing 接收 / 收款方 are not coerced into supported summary schemas, code 7a7258e8b49198f7216714a4a7748637f2ef25fd; synthetic table header tests 293d02af2d09a95c6b41df7cfe1721d08ff53a49.
- Both split and trade bill currency columns are strictly checked, including blank, foreign and conflicting dual-column entries. Latest source commit 8854b0ca438632214213bc6205cadbbedc004725; regression commit 167b3b7b69f590bf057da49fc9c90ec8c16085ab.
- These are partial trust-boundary fixes, not certified official receiver-detail schema or Finance reconciliation. Phase-one/phase-two task groups remain PARTIAL. Current Hosted source run 39031100111 is pending outcome at writing; do not mark PASS without exact SHA confirmation. Next independent development nodes: authoritative bill receiver row mapping; provider applyment dynamic conditions; four-role browser E2E and customer project flow.

- Verified official WeChat partner reference https://pay.wechatpay.cn/doc/v3/partner/4012761140 establishes that split bill detail rows are individual split OR return operations and a separate summary section has its own header, with amount fields denominated in yuan and no failed splits listed. Therefore receiver/return detail must remain UNKNOWN_SCHEMA in the current parser until a faithful source-backed adapter is implemented. Existing aggregate synthetic coverage is not a substitute. This checkpoint does not permit posting, repayment, or Finance settlement.
- Hosted source regression 293d02af2d09a95c6b41df7cfe1721d08ff53a49 succeeded (run 39031005793; optional mini jobs SKIPPED). More recent strict currency column regressions have separate CI and must be checked at their exact SHA.

## 2026-10-17 continued payment/merchant safety work (next sequence)

- Split bill receiver/detail headers containing 收款 are now held as UNKNOWN_SCHEMA rather than aggregate rows: fd2e474a5b9857868de8798cd20fc67c29b51fac; test 3b73df669ae81dd004ba856ebc636b101656837d.
- WeChat applyment GET must never replace a previously saved provider_sub_mchid for the same original application; code 3adb2b1e2398bb0d53e8d4589c20cabff93b10ed, isolated regression 15d3193145efae708e0eec26dc358d9e10137805.
- Running hosted source test for these exact commits, latest run 39031390137. Never imply live WeChat signature tested: the new identity-conflict test stubs provider transport. No production mutation; all original security gates remain unchanged.
- Next independent work remains detailed official partner bill format adaptation, broad merchant/consumer/platform E2E, and verified CRM/Finance external admission; 5 Phase-1 and 7 Phase-2 large groups are still PARTIAL, not 0% or completed.

## 2026-10-17 WeChat submerchant post-submit recovery increment

- Exact original persisted application intent (business_code, SUBMISSION_UNKNOWN state, version) is now required before storing the response of the once-only real-merchant POST. Source commits e7e04d9ebb83102c1c046f7668fdb8b94d15a7b6 and 63ace04366dc4b6d812ba6175757dee5ed7796cb; regression tests 46385aa871f7efc192dd744ff005d986ce202dc7. Mismatch remains UNKNOWN/QUERY_ONLY and never blind resubmits.
- Original production submit_enabled gate stays false by default; no merchant profile, financial receipt, or production grant was added. In-flight responses and terminal states are protected without treating synthetic test stubs as live WeChat evidence.
- Latest exact source CI run https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39031635282; confirm terminal result before stating PASS. Remaining Phase1/2 groups PARTIAL.

## 2026-10-17 Finance observed-refund numeric integrity

- `community_financial_views.py` now rejects invalid signed-refund event amounts (boolean, zero, negative, float or text) before calculating total refund observations, rather than using untrusted arithmetic. Source `19dee4d02e43d3bad2c0819003e4363c9cffbe33`, synthetic regression `b197323a01e9e83ce780f949f09259c3f120b085`; no new Finance ledger or settlement authority.
- Exact Hosted test run `39031805606` must be checked before marking PASS. Previous original merchant applyment commit `46385aa871f7efc192dd744ff005d986ce202dc7` passed Hosted test run `39031635282` (optional mini jobs skipped).
- The source tests validate internal record integrity only. Real refund, official split bill acceptance and Finance authority remain independent blocked gates.

## 2026-10-17 finance read isolation continuation

- In-place original financial_records views reject missing/malformed persisted provider records and require both the stored scope hash AND actual stored tenant/merchant/store scope to match the currently authenticated Center finance grant. Source commits ebf0e545d8b699713239b65455aa9df8001ad863, 68474162a22340058a33334acc941da6102e1217, 0ecc9f57128d4f0b51f69c7726492b57c7922bf8.
- New regression tests tests/test_community_finance_record_isolation.py validate return and split/refund scope exclusion, including a forged matching scope digest with a different stored scope (commit 82a953dfb7140e7054e619efa2862349d259b0b6). No new ledger or grant.
- Exact Hosted test run 39032389107 is pending as this checkpoint is written. Both phase groups remain PARTIAL. Continue source E2E and official provider bill detail adapter when schema documented.

## 2026-10-17 resumed project-wide finance / platform E2E

- Source code commits: finance pagination excludes persisted records outside original authenticated scoped `scope` and `scope_hash` (ebf0e545d8b699713239b65455aa9df8001ad863, 68474162a22340058a33334acc941da6102e1217, 0ecc9f57128d4f0b51f69c7726492b57c7922bf8). Corrupted original signed order evidence is fail-closed (caddc2b61edce624258a22230804d1098bac7cb8). Platform financial overview reuses the same trusted refund-total helper (999a1ec53f0c2bed5925bd70688350b02b5417af). No Finance settlement authority is invented.
- Scoped finance bill page now exposes merchant ID and currency columns useful for discrepancy tracing while omitting consumer OpenID/bank card identifiers. Source 22292e4ee3e8a6c8da22aace6d2480b020de8fa0; tests 0f8cc90a271b39d9e6f6b948589220523cd98cf0.
- Added original Center integrated synthetic scenario: consumer joins original community, orders from catalog, original scoped signed-payment projection, platform signed totals, signed bill-ticket hash and daily reconciliation, all while `finance_status=UNCONFIRMED`. Test tests/test_community_integrated_platform_bill_journey.py commit f405fb8c01723df5c4e9cfde23df7517f52ef2ce. This does not simulate live merchant, real funds, issued Finance receipts or full phase signoff.
- Current Hosted run 39032951455 for exact integration source is IN_PROGRESS at creation; check real CI terminal outcome. Original system pinned Core/Source/Runtime remain unmodified. First and second stage groups still PARTIAL.

## 2026-10-17 original scoped WeChat bill audit UI integration

- Existing `COMMUNITY_BILL_RECONCILIATION` encrypted Center links now carry exact original `bill_key`, `kind`, `bill_date`, `scope`, `result` when a bill is reconciled. The event still keys SHA256(original bill key + result), with read-side hash integrity verification. Earlier records lacking scope metadata are not automatically trusted. New read-only `bill_audit` supports strict `(kind,bill_date,after_id)` and 50-row cursor paging, always `finance_status=UNCONFIRMED`. Source 027e64eea919ebb2365fd8632124c97f338eef27 and 759e8a5f1907c86facaf4ffb247766f5783f649a, test 32e1b43af46d8de5b83be0c8594329e881546133; Hosted run 39033327926 SUCCESS.
- Original merchant workbench now displays bill API responses and read-only historical audit pagination, under existing finance workspace gate only. UI sources `demos/community-stage/workbench.js`, `.html`, latest browser check commit 642f5afb23b15463c76cf591e705c68435f4bc09. Non-finance identities cannot see the panel, and server remains original finance-authorized. Backend does not issue new financial receipts, operations or price changes.
- Current browser-integrated Hosted run 39033750602 must be checked for exact terminal CI before PASS. Both phases remain PARTIAL and shall only be audited after development is completed.

## 2026-10-17 uninterrupted execution verified end of this tool session

- Branch source work since verified baseline 8bdcd6bf239785934a4d3889f9239c940048717a produced 37 commits through governance registration d5da7a8d4dd0282df3ac15d7bbd48d3f359188cf, including original scoped financial evidence, immutable bill-audit, platform financial overview, official bill workbench, and original Center integrated business-chain test. GitHub comparison confirms original scripts/pr122_customer_core.py, scripts/pr122_customer_source.py, scripts/pr122_customer_runtime.py were untouched.
- Most recent verified exact source CI: commit 642f5afb23b15463c76cf591e705c68435f4bc09, GitHub Actions run 39033750602, test job 117399331268 SUCCESS: community 448/448, Stage 342/342, Node 34+40+8+7 pass. Optional runtime/SDK/preview checks SKIPPED. Later changes were only registered documentation/metadata, not source code.
- Feature registration now includes merchant workbench UI and browser CI paths. Other completed source tests remain reusable. First and second phase original groups (5 and 7) remain PARTIAL until complete requirements trace, official WeChat receiver-detail schema, payment/CRM/Finance external binding and phase-independent review; do not inflate percentage.
- This is a recoverable stop point for the current tool interaction, not proof that automated AI development will continue after chat ends. Resume by fetching current remote HEAD and tree, verifying single writer, and continuing unsigned external-independent source work; no Work/Codex or Dots reviewer login used.

## 2026-10-17 bill CSV input fail-closed hardening

- Source 68b9e2b25fd0e0817d4babd0f3894341eb2f12ba and 0b3b135a8528e36dfa34146cc5342d642ea76656 reject blank/invalid CSV column headers and malformed UTF-8 without disclosing raw imported customer data in error text. Synthetic parser regressions c9b0c0c1ae438ccc6ba69c88058bd431902d952f and 65acc5fbeee5ed0170bd55d3a39dc83ac994424c.
- Exact source Hosted run 39037981766 is still awaiting terminal result at checkpoint time; SKIPPED jobs cannot count as PASS.
- Source scope remains original audited official-ticket/hash validated private bill, not receiver-level merchant official schema acceptance, Finance receipt authority or live funds. Both Phase1/Phase2 remain PARTIAL.
