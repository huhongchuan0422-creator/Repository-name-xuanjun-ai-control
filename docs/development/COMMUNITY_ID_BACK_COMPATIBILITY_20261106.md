# Original OCR API compatible successor and ID-back integration

Status: unpublished local candidate. No commit, deployment, production access, real image transfer, credentials, or payment operation was performed by this change.

## Provenance and scope

- Original repository: `huhongchuan0422-creator/Repository-name-xuanjun-ai-control`.
- Original commit: `90aca1cfca1ec2a354950c394a4b0c2689b37d13`; tree `cdb3918520b176286af570101c75885bcf07cde4`.
- Original API SHA256: `0aa40ec64550b64c33bec4902d83155bcd19ab97cae7ea2b28874b28c222621c`.
- Candidate API SHA256: `32cf647f56f9f1fbed9d0c7d15bb50a0f60a9cd5124bd5ff835129196766636e`.
- Reviewable patch: `deploy/community-preview/ocr-id-back-api.patch`, SHA256 `96e72e250a1288a48a69039c5fce5bd2505e120de2e9509e333a1ff1c7da796d`.
- `secure_store.py`, `ocr_core.py`, model files, model hashes and access checks remain unchanged. `source_sha` describes the original source, not a fabricated candidate commit. `upstream_files` preserves its hashes; `files` describes exact composed candidate bytes.

The original API rejected `id_back` before inference. The candidate explicitly adds `id_back` and its confirmation keys. It does not relabel a back image as `id_front`, mutate API globals at runtime, or fork a separate store. It also preserves a small named set of inference metadata: orientation, image dimensions, correction, coordinate space, rotation marker, unresolved validity candidates and warnings. Arbitrary callback keys are not copied.

## Material, field and confirmation contract

- `business_license` resolves only original business-license material.
- `id_front` resolves only original `identity_front` material for an ID-card selection.
- `id_back` resolves only original `identity_back` material for an ID-card selection.
- Back fields: `issuing_authority`, `valid_from` (`YYYY-MM-DD`), `valid_to` (`YYYY-MM-DD` or `长期`). Ambiguous/missing suggestions remain editable and do not fabricate values.
- Explicit human confirmation persists all three fields in the existing encrypted OCR record. Recognition/read/polling never confirms or fills form values.
- Explicit fill maps `valid_from` to `subject_info.identity_info.id_card_info.card_period_begin` and `valid_to` to `card_period_end`, filling empty destinations only. Existing manual values survive. The official provider schema has no issuing-authority field; its value remains in the OCR confirmation and is not sent as an invented provider field.
- Existing owner/session/source bytes/SHA/scan/expiry, application revision and provider version checks continue on submit/read/confirm/fill. Replacing either material changes the original application revision and invalidates old job bindings.
- The v9 legal-document group remains one group, with separate human-face and national-emblem recognition buttons. Uploading a back material starts `id_back`. Side switching, late responses, unconfirmed local edits, pending confirmation recovery, source replacement and focused fields use existing request-generation and scroll guards.
- Direction text reports only explicit direction evidence; ambiguity does not pick a direction. Source boxes are OCR line-level geometry, not asserted character-precise boxes. Dates on a shared OCR line can share that line's box. Candidate boxes remain evidence, never human confirmation.

## Business-scope input removal

The user's latest request excludes business scope from all new OCR targets. New license extraction, orientation scoring and editable suggestions exclude `business_scope`; its printed label remains a layout boundary to prevent scope text from leaking into other fields. New native confirmations contain only visible supported fields. Historical raw results, encrypted confirmation snapshots and idempotency responses remain readable; reopening a legacy job does not display or silently reconfirm its business scope. Existing pending confirmations still resolve against their original complete snapshot.

The official ordinary service-provider application API is `POST /v3/applyment4sub/applyment/`, documented at https://pay.wechatpay.cn/doc/v3/partner/4012719997 (page updated 2025-03-26, verified 2026-11-06). Its business-license object does not request a business-scope text field. Required industry selection (`settlement_info.qualification_type`) and any applicable special-qualification images (`qualifications`) are separate and unchanged. Original drafts, manual profile values and other OCR fields are unaffected.

## Unchanged operational boundaries

The original applicant admission, legacy scene permission behavior, image/source size and pixel boundaries, tenant rate limit, owner queue, timeout and idempotent-resume behavior remain in place. No new role, customer whitelist, fee, credential, externally accessible endpoint or approval step was introduced. The four-rotation inference work and its real-image/resource acceptance are verified separately by the mapping workstream; this document does not claim they passed.

## Packaging

Both image Dockerfiles carry the exact candidate API. The UI-successor image additionally copies the updated bridge, dependency manifest, identity parser and runtime tests. Offline bundle extraction verifies the old original bundle before overlaying the explicit candidate API; it does not alter the source archive. The review package includes the API, patch, parser, new tests and synthetic geometry fixture. Final source-generation and image stamp must be frozen after parser acceptance, not before.

## Local verification

- Mini-program Node suite: 771 tests passed, 0 skipped. Includes side-specific upload, date fill, no overwrite, late-side response, focus/scroll, reopen and direction-warning regressions.
- Actual FastAPI successor plus original encrypted store and original Center material binding: 12 focused ID-back and legacy-license contract tests passed, covering all three types, original API historical confirmation compatibility, exact patch/hash provenance, mismatched side/type rejection, durable encrypted confirmation, original-submit replay, source replacement and blank-only date fill. Inference is explicitly synthetic in this suite.
- Wider source/API/applicant/shared-draft regressions: 93 tests run, 92 passed and 1 original real-engine-environment check skipped because model runtime was not staged in that local process. This is not a full real-image pass.
- Isolated runtime byte/real HTTP/store tests: 2 passed, including nonempty orientation/warnings persistence across GET, confirm and store reopen.
- Original owner UI guard: 11 assets matched the preserved owner baseline. Runtime-copy/read-only package check passed.

Real-document orientation/mapping accuracy, final same-image runtime testing, final frozen stamp, and any publication or deployment are separate acceptance steps. Do not treat this local report as production delivery.
