# Exact UK preview update / recovery candidate — PREPARATION ONLY

## Reused, independently accepted baseline

31d3c93b8492252cf08b95e24eb950b23b4d38ef / Tree
6becea5e51ee52e776d28133f1f3d72f5f44b0a0 is root scope PASS. Run40057093667,
job120762355537 actually passed 48 Python +19 Node; root also passed six real
HTTP/encrypted Store/original Center boundary checks with explicit synthetic
inference/admission. Reuse them without repeating algorithms, pictures or the
same tests. The new preparation commit has its own push evidence and source
artifact; its source SHA/Tree/run/artifact MUST NOT be replaced by the old run.

Original baseline Artifact12546260661 =986705 bytes, archive SHA256
247b5c7e2e482d166483fa9df1596ff41d55fcb8a68b0f615b02511eabd9d2e5;
internal source ZIP=4359967 bytes, SHA256
00bc3d44ab75f6b2109ca842911a129868dc9a1493bfea9a15271ce83ee2e869,
424 files verified against exact Git bytes. These identify the baseline only.

OCR lock remains 90aca1cfca1ec2a354950c394a4b0c2689b37d13 / Tree
cdb3918520b176286af570101c75885bcf07cde4; exact three-file SHA256 values remain
in scripts/community_ocr_dependency.json. No OCR or business source is changed
by this deployment preparation. Real ocr:use mapping, protected Store authority
and installed runtime remain separate unproved gates. OCR stays disabled; the
ordinary preview can be prepared without enabling OCR or inventing grants.

## Current real observation, separate from the new candidate

Owner-approved once-only 03:00 UK observation: current container/image/recheck
OBSERVED, running=true, original nonroot user MATCH, identity_image_state MATCH.
Root verified OCI revision 2330dd55c07f58d7f45a7c4510a9761d0d4735d6 directly from
the original screenshot. HTTP200/READY proves only
PROCESS_AND_DATABASE_CONNECTIVITY. runtime_source_sha/version_source/
backend_observed_at/freshness and runtime/image version relationship are
UNKNOWN. Overall HOLD_PARTIAL_OBSERVATION, preview HOLD_NOT_EVALUATED,
production_acceptance=false, snapshot_atomic=false. No site recheck is done.

Existing historical receipts and before-2330dd55 rollback remain preserved.
Do not substitute their IDs/image/source for current observed values. The old
community_preview_upgrade.py has fixed historical input IDs, image/artifact
hashes, source and rollback names; changing its SOURCE alone is unsafe. It and
the superseded domestic deploy.sh are NOT run or mechanically rewritten.

## What the new source actually prepares

scripts/community_preview_release_plan.py is a pure offline review compiler
and transition model, with no process/network/host/file-write API. It accepts
strictly projected source/current/image metadata, checks exact SHA/Tree/run/
source archive correspondence, nonroot identity and protected reference digest
shape, and produces review-only original Docker argv arrays and rollback
conditions. Supplied metadata is evidence to be independently verified, NEVER
permission. No caller's approved/verified/path/secret keys are accepted. All
outputs retain executable=false and execution_approved=false. Missing current
or image metadata yields HOLD with no action arrays; it does not fill fake IDs.

This completes an auditable transaction specification, NOT a privileged live
executor or durable journal implementation. A protected executor and exact
single-attempt root approval must still be independently reviewed before site
execution. Its required journal semantics are explicit, not claimed tested on
the server. The tests prove only compiler validation and transition constraints.

| Boundary | Fixed original contract |
| --- | --- |
| Future control process | original authenticated UK Workbench + separately authorized sudo/root; no new account/grant |
| Application process | UID:GID10001:1008, nonroot, read-only rootfs, cap-drop ALL, no-new-privileges |
| Resource envelope | original 0.5 CPU/512MiB memory+swap/64 PIDs, bounded tmpfs/logs; actual current projection must match |
| Config/data | same /var/lib/xuanjun-community-preview/config read-only and data writable; original keys/accounts/database reused, never replaced or printed |
| Socket/ports | same /run/xuanjun-community-preview/preview.sock; no published TCP port or new listener |
| Docker access | original /usr/bin/docker --host unix:///var/run/docker.sock; no pull or caller-selected image |
| Routing | no Nginx/DNS/certificate change; community route file digest only, no P2 runtime/data reads or modifications |
| Image | exact new same-source image ID plus archive digest; RepoDigest may legitimately be absent for a local image, not fabricated |

Protected reference digests mean hashes of typed identity/projection metadata
or existing protected backup references, not plaintext config/secret/DB bodies.
The compiler validates shape/correspondence; it cannot authenticate those
references or prove actual mount isolation from JSON alone. Original inspection
must be supplied by root's approved channel, not newly collected here.

## Serial update and known-failure recovery

Freeze exact candidate source/Tree/OCR lock/source artifact/image artifact and
current container ID/image/config/data/routing/isolation/backup identities.
An attempt and retained-container name derive from new source and current ID,
so they cannot collide with historical before-2330dd55. Review the full names
before use. Never create a new attempt after finding a partial old attempt.

Before each sensitive stage the future executor must recheck current metadata,
observation freshness, ownership/parent chains/no symlinks, original mounts and
protected references. Require root0700 attempt directory, exclusive/no-follow
root0600 intent/receipt files, fsync file+directory and durable before/after
records. Refuse stale or partial state. These are executor preconditions; the
compiler does not create those directories or imply they exist now.

The serial sequence is: durable prepared receipt → stop exact old current ID →
prove stopped and own socket gone → retain/rename that old ID → run exact new
image with unchanged contract → persist actual returned 64-hex new container ID
→ private/public exact-source fresh health and stable identity checks → durable
success receipt. No start of two writers, arbitrary image load, route reload or
database migration is added. Old config/data/accounts and all rollback objects
remain. No deletion or prune action is allowed.

On a known failure AFTER an exact new-ID receipt, persist failure/recovery
intent, stop that exact new ID, prove stopped/socket absent, retain failed new
container, restore retained pre-change old ID/name and start only that old ID.
Verify its original image/config/data/routes and process/DB health. Legacy old
runtime lacking a stamp can be restored, but preview stays HOLD. Database
downgrade compatibility and backup recovery must be reviewed separately; never
restore a DB automatically or claim Docker stop/rename/run is atomic.

Timeout, missing/ambiguous run receipt, changed IDs/references, socket still
present or uncertain new writer status → HOLD_INSPECT_SAME_ATTEMPT. No blind
retry, new attempt, second writer or automatic old start. Recovery transitions
cannot skip proof that the new writer stopped. Rollback itself can fail; then
retain exact receipts and STOP, not claim atomic recovery succeeded.

## Same-version health gate

Reuse original runtime stamp chain: Dockerfile SOURCE_SHA → immutable
/app/COMMUNITY_SOURCE_SHA + COMMUNITY_SOURCE_SHA + OCI revision. Original
community_mini_http.runtime_version binds file+environment at composition.
Fixed uk-path-candidate health URL, no redirects, JSON<=4096, HTTP200/READY,
scope PROCESS_AND_DATABASE_CONNECTIVITY, production_acceptance=false. Require
remote runtime_source_sha==new image OCI==exact accepted source SHA;
version_source IMAGE_BUILD_STAMP, integer observed_at no older than600s and no
more than30s ahead. Bind stable pre/post actual container and image identities.
Current image OCI alone or local GITHUB_SHA is not remote runtime proof.

## Accurate remaining evidence, once only (no connectivity recheck here)

1. New same-SHA image has NOT_EXECUTED build status; image ID, optional RepoDigest,
   inner image-tar digest and image-artifact outer digest do not exist for this
   candidate. Do not copy the baseline source ZIP SHA into image fields.
2. From root's existing authorized original observation/reference material:
   exact current container ID and image ID; protected original config/data,
   community-route and full isolation projections; backup/recovery reference
   and downgrade compatibility. Summary OBSERVED/MATCH is not their raw values.
   No secret bodies or new credentials are requested. If these were not captured,
   root decides any later minimal observation authorization; this window does not
   probe or ask Owner to invent values.
3. Independent candidate review and a separately approved exact journal/executor
   attempt. No approved executor or site receipt is fabricated by this plan.

## Original image and official Mini preview next inputs

Original workflow community-backend-image builds verify/release targets from
the SAME RUN validated source ZIP, using original pinned wheel hashes and
Dockerfile. Its existing trigger is a normal push whose commit message contains
[community-image]. This preparation does NOT include that marker or build.
workflow_dispatch currently has NO image-enable input, so do not claim dispatch
can build the skipped image at this SHA. A later authorized normal reviewed
source change/build must bind its own new SHA and CI, or root may review a
minimal opt-in on that same original workflow. No dummy push/new channel here.

Use the original preview workflow exact existing path .github/workflows/chatgpt-community-wechat-sp-offline.yml and
original community branch. The delivery's generated manifest supplies exact
preview_source_sha and preview_evidence_run_id from THIS new push. Existing
inputs: preview_enabled=false (only later explicit approval may set true),
preview_target=uk-path-candidate. Require selected branch HEAD==run SHA==input
SHA, successful completed original test evidence and unique unexpired digest-
bound artifact. No old31d3 run substituted for new preparation SHA.

Reuse AppIDwx1d5f8873eaea5392, miniprogram-ci2.1.31, original domestic
xuanjun-domestic-ops/nonroot githubrunner/Node20 and existing Secret references;
no values read, reinstall, grant or new key. Prepare with the existing
deploy/community-preview/prepare-mini.cjs; home entry, scene=null and blank
query. No shop1 identity is created. This is source preparation, not compilation,
QR upload or acceptance.

Later official preview receipt must bind operation DEVELOPMENT_PREVIEW_ONLY,
exact frontend source/prepared-file manifest, remote backend source/freshness,
uk-path-candidate, original AppID/home entry, payments=false and actual
DEVELOPMENT_PREVIEW_UPLOADED with preview.png. UNKNOWN/failure must retain its
real status, not fabricated success. Public review/release, real login/device
acceptance and production payments remain separate approvals and evidence.
