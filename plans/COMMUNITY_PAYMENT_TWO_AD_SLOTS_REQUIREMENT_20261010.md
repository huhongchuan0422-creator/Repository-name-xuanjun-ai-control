# Community payment split: two advertiser-managed placements (Owner requirement 2026-10-10)

Status: REQUIREMENT_APPROVED / IMPLEMENTATION_NOT_STARTED.
Architecture scope: V2.7 Stage 5, XUANJUN_CAUSE_COMMERCE_PAYMENT_V1, nodes 5.7 Advertising and 5.8 Admin; UI hooks must be reserved when building 5.3 Payment and post-payment receipt, not deferred as incompatible refactor.

## Required customer-facing flow
1. Consumer scans merchant QR, arrives at a trusted payment amount-entry page.
2. **AD_SLOT_PAYMENT_AMOUNT**: an advertisement placement on the amount-entry page, visible without obscuring the amount, merchant, payment confirmation, consent or security notices.
3. Consumer enters amount, confirms, follows the provider-authorized payment flow; any external hosted pay page may have rules that prohibit inserting ads. Do not promise control over provider-owned pages.
4. After server-side provider verification/reconciliation confirms result, show payment-result / receipt page with **AD_SLOT_PAYMENT_SUCCESS**, a second, independently configurable placement. Do not equate browser redirect with settled payment.
5. Failed/cancelled/pending payments have truthful statuses and must never falsely display a successful paid receipt. Define a separate visibility policy for result-page ads by payment status.

## Merchant/customer administration
- Authorized merchant or organization admins can create, upload, schedule, preview, approve, activate, pause, archive, and report on advertisements assigned to their eligible merchant/store/payment context.
- Separate slot configuration, creative/media type, image/text/link, validity dates, priority, display constraints, campaign status, moderation, audit and optional frequency rules.
- Multi-tenant isolation: merchant A must never see/change merchant B creatives or metrics; platform admins have bounded, auditable permissions.
- Asset upload, URLs and redirect links require content safety, malware checks where applicable, privacy, accessibility, and appropriate legal/advertising review.
- Track ad impressions/clicks using idempotent events and honest measurement definitions, not payment or ledger data. Ads must not modify the payment amount, provider order, merchant beneficiary, charitable split, refunds, finance ledger or payment confirmation.
- One campaign may target both slots or different campaigns can be assigned to each; each slot has a fallback state when no approved active ad exists.

## Design and QA gates
- Payment status always comes from server-side verified provider evidence and reconciliation; preserve anti-replay and idempotency.
- Reserve these two slots in payment journey UI and schemas at nodes 5.3 and 5.7; implement authenticated management under existing Admin Console Framework node 5.8, not a second advertising backend.
- Test mobile amount entry, QR deep-link integrity, payment success/pending/failure, two independent slot selection rules, no-ad fallback, XSS/URL injection, abusive creative, tenant isolation, accessibility, creative expiration, impression/click dedup, performance, provider hosted-page boundaries and refunds.
- Payments must still function if ad service fails. Block ads from controlling navigation or masking the checkout/confirmation action.
- No production payment changes or customer adverts are authorized by this file. Validate payment provider capabilities, licensed merchant identity and actual flow before build/release.
