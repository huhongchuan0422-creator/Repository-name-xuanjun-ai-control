# Original shared draft source preparation — integration HOLD

Base: dc60a2660abc0ad8319c14c60f4b4205bb8f8749 (unchanged host-only dual-CAS).

## Implemented in the community source only

`MiniMerchant.ocr_shared_source(token, scene, application, kind)` is a protected
Python method, absent from the Mini/HTTP operation allowlist. It uses the
original single Center connection and BEGIN IMMEDIATE. It returns the existing
`ocr_source` identity/origin/application/current-object/verified-byte fields,
plus `wechat_version`, an exact integer from the original encrypted
COMMUNITY_WECHAT_APPLYMENT record. Absent record means original version 0;
inactive or foreign-owner records are denied, not treated as absent. Existing
records require exact positive integer versions (including rejection of bool).
Both original drafts must be editable. External transactions and non-original
service instances are denied.

Provider row owner/active/ciphertext is frozen before decryption and checked
after both source reads. Original source repeats session, tenant/project/scene,
application, attachment/object, SHA, MIME, scan and expiry checks. The final raw
platform draft must equal the initial draft. A second SQLite writer cannot
change either version during this transaction. The result is data, NOT a signed
confirmation capability and NOT authority to write.

## Defined field targets (unchanged)

| Confirmed key | Empty original destinations |
| --- | --- |
| company_name | platform.fields.legal_name; subject_info.business_license_info.merchant_name |
| registered_address | platform.fields.address only |
| IDCARD | no write target; do not invent one |

Conflicting manual names on either side suppress company_name fill on both.
Three scene photos never enter OCR. No HTTP body supplies identity/permission.

## Tests and deliberate limits

New real Center/SQLite tests take the observed integer version pair and pass
that SAME pair to the unchanged dc60 primitive using synthetic human fields.
They prove same-pair success, stale pair/replay refusal without DB changes,
manual provider edit refusal, strict types, original session/tenant/origin,
provider owner/revocation, both edit states, in-read mutations/rollback and a
real second-connection writer exclusion. This is community source→CAS
composition, NOT OCR HTTP/store confirmation→Center composition.

The current production dependency lock stays at 2dc5eeb. Candidate 514e7c2 is
NOT independently accepted: root found Pydantic bool→int coercion and mutable
confirmed_binding/eligibility issues. Do not pin it or treat those defects as
an API contract. The bridge shared-writeback HOLD stays unchanged.

## Exact remaining integration dependency

Await the OCR sole Writer's corrected exact SHA, contract and independent
review. Verify strict pre-coercion dual-version types; server resolver binding
to provider and application versions; immutable confirmed binding whose fields,
subject/tenant/app/type/attachment/SHA and human-seen version pair are preserved
by encrypted store confirmation/idempotency; GET eligibility only for a valid
confirmed binding. Only then map this internal source result to that exact
resolver signature and frozen confirmation representation. Never read latest
versions at writeback as substitutes for the confirmation snapshot.

Before any HOLD removal, test actual pinned OCR HTTP + encrypted store + real
Center using synthetic inference/admission, including forged/replayed binding,
cross-tenant/subject/application, bool versions, both stale versions, source
replacement/scan revocation, confirmation retry and human fields. Default real
ocr:use mapping remains unproved/403. Center CAS and OCR storage are separate
databases; no cross-database atomicity or production readiness is claimed.

No server, deployment, dispatch, real document, credentials, grants or provider
call is involved. Existing 66-route evidence and dc60 regression are reused.
