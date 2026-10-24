# Protected OCR confirmation → original Center dual CAS

Base: cbcace15cf337fd2c0f3d52418abe7dbcc6612d9 (source preparation scope PASS).
Supersedes the pending-dependency status in the earlier source preparation note.

## Fixed dependency, no OCR source edits

OCR source 90aca1cfca1ec2a354950c394a4b0c2689b37d13;
Tree cdb3918520b176286af570101c75885bcf07cde4.
Root supplied scope PASS for Engine40055795141/job120758381588 (56+8)
and Persistence40055795144/job120758381630 (17+3), including A→B→A immutable
response replay and revoked-source 403. Those algorithm/store suites are reused.
The community lock verifies the unmodified three files before composition:

| File | SHA256 |
| --- | --- |
| api.py | 0aa40ec64550b64c33bec4902d83155bcd19ab97cae7ea2b28874b28c222621c |
| secure_store.py | c0191b6766fc884fc4e5f32e9b6492daa5bf0d90527ab77ed2feb5bd03a05696 |
| ocr_core.py | bbc99d7e5bc606fc0f069b5a26babc4b87a5f7b4e0726cd71acab231933bc308 |

## Actual interface mapping

Original CenterIdentity merchant_context supplies the live subject, scene,
project, CSRF and business tenant. Account UID is not substituted for tenant.
No request body supplies authority. Production authenticate still yields no
ocr:use permission and the actual OCR API returns 403.

| Source | OCR contract |
| --- | --- |
| original application revision, exact positive int | canonical positive decimal string application_revision |
| original encrypted wechat.version, exact int >=0 | provider_version, original integer (absent draft=0) |
| original current scanned attachment object bytes | document_type, attachment_id, content_sha256 |
| business_license / identity_front | business_license / id_front |

The six-argument resolver is authorize_attachment(principal, application,
attachment, digest, document_type, expected_application_revision=None).
It calls the original protected source and returns both versions with the
original content/type binding. OCR freezes these at job creation. GET, confirm
and delete reauthorize current source; application or provider edits invalidate
the old job. No special provider field is invented for scene photos.

Mini read captures the server's application_revision and provider_version
alongside its existing app/job/type/request generation. Confirm echoes those
observed values; HostOcr passes them unchanged to the real OCR HTTP endpoint.
Missing, bool, floating or noncanonical community versions fail closed. The
confirm acknowledgement must match the same pair. No execution-time latest
version is used as the user's observation. Confirmation only stores suggestions;
the existing Mini HTTP response still says NOT_REQUESTED_MANUAL_SUGGESTIONS_ONLY.

## Host-only writeback and failure boundaries

CommunityOcrBridge.apply_confirmed(principal, job_id,
expected_confirmation_revision=...) reads the actual configured encrypted
SecureSQLiteJobStore. It verifies tenant, subject, job/status, exact positive
confirmation revision, allowed string confirmed_fields and complete frozen
confirmed_binding against that same persistent job. HTTP
shared_writeback_eligible and an old idempotency response do not authorize it.
An old key's revision differing from the Store's current confirmation is denied;
no old response selects the newer fields. The ID card path has no write target.

The current source and both versions are rechecked, then the original dc60
primitive receives the SAME persisted pair. Inside its original Center
BEGIN IMMEDIATE it checks ownership, session, both edit states and both CAS.
A protected source_check repeats source/type/object SHA/scan/expiry, identity,
and the current persistent confirmation before first write and before commit.
The final check permits only the primitive's own expected +1 version changes.
Changed confirmation, missing/deleted job or attachment revocation rolls back
both Center drafts and Center audit. A provider edit in the gap between the
cross-database precheck and transaction fails CAS with zero application write.

Only empty existing license targets are filled: company_name → platform
legal_name and subject_info.business_license_info.merchant_name; a conflicting
manual name on either side suppresses both fills. registered_address → platform
address only. Other confirmed certificate values remain suggestions. IDCARD
does not create targets. Three scene photos have zero OCR source/UI calls.

Center and OCR use separate databases. A confirmed/deleted OCR record can remain
so even when Center rolls back; no distributed transaction or atomic snapshot
across the two databases is claimed. Checks are at their observed points, not a
guarantee against changes after the final OCR read. There is no new HTTP apply
operation, auto-writeback, grant, credential, real inference/engine acceptance,
real document upload, deployment or production OCR enablement. Missing/legacy
frozen tuples retain OCR_SHARED_DRAFT_WRITEBACK_VERSION_BINDING_REQUIRED.
The host timeout still does not prove stopping a running inference thread.

## Validation scope

New synthetic-material tests use the actual original Center, same-thread owner
dispatcher, actual pinned OCR HTTP and encrypted SecureSQLiteJobStore. Only
inference and explicit test permission admission are synthetic; source callbacks
are the real implementation. New tests include reopened encrypted Store,
current tuple, source revocation/replacement, cross subject/tenant/application,
wrong type/same SHA, strict seen versions, default403, stale pairs, replay vs
current confirmation, in-gap CAS failure, later confirmation/deletion, source
revocation during second write, actual second-write/audit rollback, preservation
of manual fields and no ID target. Original owner/bridge regressions affected
by the new dependency and confirmation body are run; dc60 old CAS/source suites,
OCR algorithms, unchanged 66 routes and 132 screenshots are reused.

## Actual UK version / preview admission (Owner observation, no new site I/O)

Owner-approved minimal read-only candidate ran once at 03:00. Inner and outer
exit2; original admin prompt returned. current_container/current_image/
current_recheck OBSERVED, running=true, original nonroot user MATCH,
identity_image_state MATCH. Root independently verified OCI revision
2330dd55c07f58d7f45a7c4510a97610dd4735d6 from the original 03:00 screenshot.
This is the observation as supplied, distinct from older upgrade-source constants;
do not silently normalize either identifier. The observed 2330 image is not this
new community source candidate.
HTTP200/backend READY proves PROCESS_AND_DATABASE_CONNECTIVITY only.
runtime_source_sha/version_source/backend_observed_at/freshness and
runtime_image_revision_relation remain UNKNOWN. Overall
HOLD_PARTIAL_OBSERVATION; preview_acceptance HOLD_NOT_EVALUATED,
production_acceptance=false, snapshot_atomic=false.

Owner personally supplied the five existing images and both read-only scripts;
root visual scope PASS and script review are received. Old attachment-access
history does not block this independent source work. No artifacts are regenerated
or reuploaded and no site check/deploy is performed here. Actual permission
mapping, protected production dependency/store availability, runtime same-version
proof and separately authorized official preview/device acceptance remain gates.

## Existing version update path — preparation only, no execution authority

The new candidate's exact source and Tree are the delivery commit and Hosted
head_sha; record them separately from the observed current OCI revision above.
The following existing paths are reused, not a new deployment channel:

| Stage | Original path and exact binding | Present state |
| --- | --- | --- |
| Source evidence | original SP workflow test job, same-run deterministic community-stage-source.zip and manifest | await this commit's normal push result |
| Image preparation | original community-backend-image job in the same workflow, existing Dockerfile release/verify targets | NOT_RUN; no image ID/digest invented |
| Build version | SOURCE_SHA=exact accepted run head; /app/COMMUNITY_SOURCE_SHA, COMMUNITY_SOURCE_SHA, OCI revision must agree | existing Dockerfile, not deployed |
| Image artifact | original community-backend-image-candidate: community-image-tests.log, community-image-id.txt, community-backend-image.tar.gz, community-backend-image.sha256 | absent for this source until separately authorized original build |
| Site replacement | original UK container transaction design and protected mount/config/data/isolation contract | PREPARE_ONLY, not authorized or instantiated |
| Preview gate | original community_preview_readiness.py, uk-path-candidate; original miniprogram-ci 2.1.31/Node20/domestic Runner | default disabled, no dispatch/upload |

Image ID, RepoDigest (if present), image-tar SHA, outer artifact SHA and source ZIP
SHA are different values. Before a replacement is executable, root must review
the exact new same-SHA image artifact and current observed ID/image/mount/config
identities. The user's summarized 03:00 observation proves OBSERVED/MATCH but
does not supply those complete current ID/image values here. Do not fill them
from the historical receipt, old image constants or a guessed path.

The old scripts/community_preview_upgrade.py hardcodes its historical SOURCE,
IMAGE, OLD_IMAGE, OLD_ID, artifact hashes and names. It is not a generic updater:
DO NOT run it or change only SOURCE to this candidate. The domestic deploy.sh
is superseded and is not the UK update path. No new privileged installer or
site mutation is added by this package.

The smallest later UK transaction candidate must freeze this new image ID/tar
digest and the actual pre-change current container ID/image; preserve the
original /var/lib/xuanjun-community-preview/config (read-only) and data (same
original database), /run/xuanjun-community-preview socket, original UID/GID,
limits/network/capabilities and existing routing. It must refuse changed input
identities, missing backup/recovery evidence or an unexpected existing writer.
No P2 route editing, config/secret reading, new identity or database replacement
is implied. This preparation does not prove database downgrade compatibility.

Rollback must reference the pre-change *current* container/image fixed by that
new transaction, not the older before-2330dd55 container. Keep both historical
objects/receipts. Retain the stopped old current container and bind its exact
ID/image/config/data identities in the new transaction receipt; use a distinct
reviewed attempt/name without overwriting historical names. On known failure,
prove the new candidate stopped before restoring the exact retained prior
container. On timeout/unknown partial mutation, stop and inspect the same
attempt; never blind retry, automatically start a second writer or replay the
historical updater. No rollback is executed here.

Health acceptance remains the existing strict gate, not HTTP200: fixed
https://uk.wenwenwenyiyiyi.work/community-preview/community/health, no redirect,
JSON <=4096 bytes, READY, exact PROCESS_AND_DATABASE_CONNECTIVITY scope and
production_acceptance=false. Remote runtime_source_sha must equal the new
candidate's actual accepted source SHA; version_source IMAGE_BUILD_STAMP and
integer observed_at within 600 seconds (at most 30 seconds ahead). Bind the
responding runtime to the observed candidate image's OCI revision and stable
pre/post current container identity. Missing runtime SHA/stamp/freshness or any
mismatch remains HOLD even with image revision observed and HTTP200. The
current 03:00 report therefore does not admit this candidate.

One later approval package needs: accepted source/CI/internal source hashes;
same-SHA original image build/verify evidence and actual image identifiers;
root's current observation identities and protected config/data/rollback
bindings; independently reviewed exact transaction attempt and recovery plan;
then explicit Owner execution authorization. None is fabricated by a plan.
Official preview subsequently needs the same frontend SHA/prepared manifest,
same-source fresh backend proof, exact successful push evidence, original
branch/run/input SHA and uk-path-candidate. No production OCR enablement is
required merely to prepare an image; real ocr:use, existing protected store and
the locked dependency runtime remain independently unproved and disabled.
