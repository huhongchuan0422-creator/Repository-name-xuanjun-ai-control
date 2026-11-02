# Community split opt-in checkpoint — 2026-11-01

## Scope and writer reconciliation

- Continued the existing `feature/community-admin-ocr-successor-20261031` worktree at commit `5e26425d58bc2a1102a50be8aae3053200f6f875`.
- No process writing this source tree was found before editing. The observed community preview process runs the installed `/opt` release and was not treated as a source writer.
- Preserved the existing uncommitted R2 admin-page changes. No reset, checkout, package rebuild, deployment, provider request, payment mutation, credential read, or account mutation was performed.

## Pre-edit byte anchors

These hashes were recorded before this task changed the files:

| File | SHA-256 |
|---|---|
| `demos/community-stage/onboarding.html` | `c25307d381b5cc0917edb436eb5194a991ce7d27980f410349293f387db97384` |
| `demos/community-stage/onboarding.js` | `4e7528126e5f1996a92717f41ac05ed79fda64630b3faa718327e701a9cbac5d` |
| `scripts/community_merchant_onboarding.py` | `374c32c2d2889b34f16af7a2f184b56023e7bf00abb09e252ec671158c76b8a0` |
| `scripts/community_mini_application.py` | `33566ac76229ae4c4d893f41ad98218672738ead6cf594aaa23dbfe951820268` |
| `scripts/community_wechat_payment_activation.py` | `7771d1b3995077b3fc42778847d65bec7a2146c321e52cd809d57338c04acfc7` |
| `scripts/community_wechat_sp_actions.py` | `5fe5959aff42d5ad6e0a14c66568841936df1ba39cb5c7207167c8f7f8707424` |
| `scripts/community_split_rules.py` | `9db1d84607a651e9ed74dbab01caf567c5700d80a6ce0f547cab78dcbb39f35f` |
| `scripts/community_reports.py` | `cfdd9c206639b0a4421a87c7f9ed57ad44f1df9eb263744baf6bcd9abbc01698` |

## Implemented behavior

- Merchant split participation is opt-in. Missing/legacy fields read as `split_participation=false`, requested/effective ratio `0`.
- A participant must submit a positive integer basis-point ratio (`1..10000`). Participation and ratio must agree.
- Approval obtains the maximum from the existing protected provider action binding (`profit_sharing`, `max_total_bps`); an opted-in request cannot be approved when the maximum is unavailable or exceeded.
- Review/applicant projection shows participation, requested ratio, current WeChat/provider maximum, and effective ratio separately.
- Existing points redemption remains a separate `0/10/20/25/30` field and is tested independently.
- Non-participants are denied before community receiver binding, split-rule creation, and provider split execution. Payment projection sets `profit_sharing=false` for non-participants.
- Existing service-provider applyment/payment/provider-action composition is reused; no second merchant, payment, or task system was added.

## Verification

- `84` affected Python tests passed in the existing preview image (`Python 3.11.17`), with network disabled, source mounted read-only, and a temporary `/tmp`:
  - split opt-in, onboarding, points, payment activation, earnings integrity, community reports, and admin information architecture.
- `node --check demos/community-stage/onboarding.js`: PASS.
- `node tests/community_management_filter_helpers.cjs demos/community-stage/workbench.js`: PASS.
- `git diff --check`: PASS.
- The successor runtime stamp was mechanically refreshed after the combined R2 + split opt-in bytes were frozen; its two exact-copy/package binding tests pass. No image was built or deployed.

## Remaining gates / human actions

1. Independent review must cover the combined current R2 bytes plus this increment on one fixed commit/artifact.
2. A protected commerce-policy owner must verify each real merchant/store binding's WeChat-authorized `profit_sharing` state and `max_total_bps`; no real merchant was queried here.
3. A real merchant must voluntarily choose participation and ratio; a reviewer must approve only after the protected maximum is available.
4. Real WeChat receiver-relation creation, signed provider calls, staging/install, read-back, and real-machine acceptance remain unexecuted and require the existing release gates.
