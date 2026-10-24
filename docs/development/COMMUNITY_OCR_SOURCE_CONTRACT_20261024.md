# Issue76: community-side OCR source contract

Current status: pinned OCR **2dc5eeb1**, real-source HTTP/store composition tested; production admission and host composition remain HOLD. The current mapping and limits are in “Superseding community composition” below. Earlier sections are preserved historical analysis.

## Historical source preparation (5b6/837)

This is source preparation, not deployed authentication, OCR inference, HTTP integration, official device acceptance or merchant approval. The only OCR API inspected is PR139 commits `5b6a46a743852dac9c25090e428a2b71e3e0ad9b` and `837f72487ea9ae8e5f39f18b3adce4ded48b3019`. Both API files have SHA256 `4d674ee22d66df2d92b21a955109c91dc946f993fb5406ced913fb27e7a6c757`. No OCR source is copied, changed or substituted here.

## Existing authoritative chain

| Value | Original server authority / function |
| --- | --- |
| Login subject | `CenterIdentity.merchant_context(token, scene)` -> `_resolve` -> `Center.session`; current `WECHAT_MINI_SESSION` and `WECHAT_MINI` links, project/registration permission, current epoch and maintenance gate. `uid` is the subject; no client-supplied user or verified flag. |
| Business tenant/project/store | Registered scene -> original Principal -> runtime binding scope; `_resolve` checks project tenant against Principal tenant. Never use the onboarding table's `tenant` column as business tenant: that existing column is applicant UID. |
| Application owner | `MerchantOnboarding._load(application, uid)`: active `COMMUNITY_ONBOARDING` link, owner UID, encrypted metadata, original workflow application. |
| Application origin | New applications created through `MiniMerchant.dispatch` save a server-derived `ocr_origin` in the existing encrypted metadata and original save transaction. Contains project, scene, business tenant/merchant/store scope. Client body schemas do not accept it; subsequent saves do not replace it. No new table, grant or credential. Old/web-created applications without origin are refused for OCR; no historical attribution is guessed or migrated. |
| Attachment | Current metadata material kind -> `object_id`; original `objects.project` must equal the application, scan CLEAN, stored SHA must equal metadata SHA, expiration checked. Replaced historical objects are not treated as current attachments. |
| File bytes and SHA | Decrypt original private encrypted object using `object:<application>:<object_id>` AAD; check exact length and recompute SHA256 against database + metadata. No browser-selected file or uploaded OCR multipart digest is taken as application authority. |

## Community preparation implemented

`MiniMerchant.ocr_source(token, scene, application, kind)` is a **protected Python-only method**. It is not added to client operation allowlists or HTTP routes. It revalidates original identity, immutable application origin, current owner, scanned object and decrypted bytes, then checks identity/scope/application revision/material state again before returning. It returns `subject`, business `tenant_id`, `project`, `scene`, `scope`, `onboarding_application_id`, `application_revision`, `attachment_id`, `document_sha256`, OCR `document_type`, MIME and raw `data` for the trusted caller only. Never log or serialize this result to a public response. There is no OCR network call or claim of OCR success.

Supported mappings: `business_license` -> `business_license`; `identity_front` with original `IDENTIFICATION_TYPE_IDCARD` -> `id_front`. Existing PDF uploads remain preserved but OCR source preparation refuses them as `OCR_IMAGE_REQUIRED`; no conversion engine is invented. Storefront/interior/cashier photographs, back sides, passports and unsupported kinds are refused. The original material upload workflow is unchanged apart from storing new application provenance.

## Mapping to actual OCR callbacks and remaining hard gaps

- `authenticate(token) -> OCR Principal`: host composition must resolve the **original** token with a server-selected registered scene and map the returned UID/business tenant to the actual OCR Principal. It must revalidate each request, including session/provider/project revocation. No OCR `ocr:use`/`ocr:admin` grant is created here; the actual admitted permission mapping is still absent. Do not forward app secrets or mint a second token.
- `authorize_application(p, application_id)`: compare actual authenticated subject/business tenant and use current `_load` plus immutable `ocr_origin`; do not merely compare UID or accept the caller's tenant. A request-bound trusted composition needs the original session and scene to call `ocr_source`. That composition is **not installed**, and application ownership is not established by injecting a permissive callback.
- `authorize_attachment(p, application_id, attachment_id)`: current object ID can be bound to `ocr_source`. But the inspected OCR callback is invoked **before** reading multipart bytes, accepts only three arguments, and does not receive document type, expected SHA, bytes or application revision. Its boolean result is not compared with the later SHA computed from multipart bytes. This cannot prove that the submitted OCR bytes are the original authorized attachment. A trusted community sender can use exactly the prepared bytes, but this does not fix the gateway's acceptance contract for other callers.
- Actual OCR GET/confirm/delete paths check authenticated tenant and job subject/admin but do not invoke application/attachment callbacks. A still-valid login alone cannot attest application-specific revocation, replacement or permission on those paths. Current GET also filters confirmed fields/revision. Record these actual API gaps; do not assume the rejected API/YAML changes landed.

Required OCR handoff before enabling any HTTP connection: an accepted contract for binding actual incoming bytes + document type + application revision to the authoritative attachment, and live application/attachment authorization on job reads/confirmation/deletion. Runtime host composition and permission admission must also be explicit. Missing contract/source keeps OCR integration HOLD; no workaround endpoint is added to community.

## Evidence and limits

Focused tests use the actual original Center/session/application/scanned encrypted-object code with synthetic provider/material fixtures. They cover subject/tenant source, another owner/tenant, cross-application object, current replacement and wrong SHA, revoked provider/session, missing legacy origin, client-origin injection, scene photos and PDF rejection. They are community authorization/source tests, **not** actual OCR HTTP or real-document inference. Existing business/UI/66-route evidence is reused; no official preview/upload, credentials, deployment, payment or production operation is performed.

## Read-time revocation correction

The initial object row is a read-start snapshot only. Immediately before returning bytes, after the existing session/scope/application checks, `ocr_source` re-queries the original `objects` row by current object ID and application and compares all eight stored fields: ID, version, project, MIME, size, SHA, scan and key ID. The final row must still be CLEAN, image MIME, current material SHA, exact length and SHA256 of the already-read bytes. The original expiry is rechecked using the current Center clock at release. Missing/deleted/changed objects or expiration deny the source. Application metadata/revision and original session checks remain in place.

An isolated decrypt-time injection against the original method reproduced the reported scan/SHA/expiry defect, plus object deletion/metadata changes. Nine added test methods (including eight individual object-column mutations) now exercise the real original Center and encrypted-object path: scan revocation, deletion, metadata replacement, time crossing expiration, session/provider revocation, application revision/revocation/material replacement, and an `identity_front` positive case. This is controlled synthetic regression evidence, not a live attack or OCR HTTP success. The OCR gateway contract HOLD described above is unchanged.

## Superseding community composition: OCR 2dc5eeb1

The earlier 5b6/837 gap analysis above is historical, not the current API contract.
The current dependency is exactly `2dc5eeb1d0d1ffb037314a8edcf5c2e16d645a40`, tree
`2984f51d3ed29b2cc67646b8d885c00a04c12881`. `scripts/community_ocr_dependency.json`
pins SHA256 of the three unmodified OCR dependency files. `compose()` verifies
those files and the actual SecureSQLiteJobStore class before creating the app.
No OCR engine code is copied into community source or edited by this Writer.

| Actual interface | Community source |
| --- | --- |
| authenticate(token) | original CenterIdentity.merchant_context, server-selected registered scene; UID→subject, runtime scope.tenant_id→business tenant |
| authorize_application(p, application) | current Center session/provider/project, original owner-only _load, immutable server-created ocr_origin equality |
| authorize_attachment(p, application, attachment, sha, type, expected_revision) | MiniMerchant.ocr_source current bytes/scan/MIME/size/expiry/object identity, exact attachment/SHA/type and canonical revision string |
| business_license | business_license |
| id_front | identity_front only for IDENTIFICATION_TYPE_IDCARD |
| scene photos | unsupported; no OCR |
| GET / confirm / delete | pinned OCR API calls the same current-source resolver with stored expected revision |
| apply_confirmed(p, job_id) | configured encrypted store only, confirmed subject-owned job, source recheck, fill empty platform fields only, original save revision CAS |

Original Center revisions are positive Python integers, normalized to their
unpadded decimal string. No UID→tenant fallback, request-created permission,
legacy revision invention, new grant, token, HTTP route or credential is added.
Confirmed company_name can fill empty legal_name; registered_address can fill
empty address for business licenses. Existing manual values are preserved.
Identity fields have no proven platform destination here and are not auto-written.
A successful write increments the original application revision, so the old OCR
job is subsequently rejected by current-source checks.

Original Center SQLite is **same-thread**. `compose` therefore requires a protected
host `owner_call` dispatcher to the existing owner loop, and every source callback
checks that it actually runs on the thread where the bridge was composed. No
`check_same_thread=False`, duplicate Center/DB or guessed production queue is used.
The composition test pumps that real owner loop while sending actual multipart,
GET, confirm and delete requests through FastAPI TestClient/ASGI transport. This
is HTTP contract composition, not a deployed network endpoint or inference proof.

### Actual remaining HOLD

1. Repository search found no existing authoritative `ocr:use` mapping. Production
   authenticate returns the real subject/tenant with **empty permissions**, so
   the actual OCR API rejects with OCR_PERMISSION_DENIED. No permission callback
   is invented. TestAdmission is explicitly test-only and has no production path.
2. PlatformHost has not yet admitted an OCR service plus its serial owner-loop
   dispatcher/configured encrypted store. `compose` is protected preparation,
   not an installed service. Its dependency pin is not a deployment instruction.
3. Tests inject synthetic inference; real OCR Engine/Persistence evidence at the
   pinned SHA is reused separately. No real document, engine execution, provider
   request, official preview or QR code is claimed by these tests.

Admission/host composition and the shared-draft writeback boundary remain HOLD;
the real-source resolver and encrypted HTTP composition can be reviewed now.
Final official same-version candidate must follow admission resolution; do not
upload the older 125 candidate as though this connection were installed.

Writeback compatibility boundary: when original WechatApplyment is configured,
original save can synchronize names/contacts from its separate provider draft.
There is no proven dual-version OCR/provider CAS in that path. A would-write
operation therefore rejects with
`OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED`; no new provider field or
revision contract is guessed. Confirmation storage and manual-field preservation
remain testable independently. Unconfigured original onboarding uses the proven
application revision CAS for empty-field writeback only.
