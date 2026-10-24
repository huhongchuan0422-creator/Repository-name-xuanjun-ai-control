# Original host and Mini OCR preparation

Default PlatformHost has `ocr=None`. Only protected Python composition
`host.configure_ocr(registered_scene, pinned_2dc_api, existing_secure_store)`
opts in before listening. No plan/env/body enable flag, secret lookup/key creation,
permission grant, additional Center, listener or production execution is added.
The existing SecureSQLiteJobStore must already have a protected directory/file;
its real type and pinned unmodified OCR sources are checked. Host close first
rejects pending owner calls, then closes the original application/Center/runtime.

OwnerCalls uses the original thread, max eight queued calls, five-second timeout,
no automatic retry; cancelled/expired pending calls never execute. The HTTP/ASGI
worker never uses Center directly: callbacks return through the owner queue.
Host request timeout closes the lifecycle, denies further calls, and discards
late results. This does not claim to forcibly terminate an already running OCR
inference thread; no engine/model execution is enabled without original authority.

The existing `/mini/merchant` operation `ocr` accepts only submit/read/confirm/delete
schemas and original session/scene. Submit obtains bytes/type/attachment/revision
from current server source, never HTTP file bytes or tenant/permissions. Job reads
require current subject/application before invoking the original OCR HTTP paths.
Missing `ocr:use` still returns 403. Only three fixed feedback codes cross the
Mini transport: OCR_AUTH_DENIED, OCR_SOURCE_CHANGED, OCR_UNAVAILABLE.

Native certificate-only controls display current-source suggestions, allow human
editing/confirmation storage, and clear stale suggestions on reload/logout/scene
switch/source revocation. Local dirty/version changes prevent confirmation. No
suggestions auto-fill the application or provider profile. IDCARD front uses
id_front; other identity types and three scene photos do not trigger these controls.
HTML projection explicitly remains isolated with no OCR service or sample fields.
No shared-provider dual-revision CAS exists: protected bridge writeback continues
to reject that path; identity has no new destination fields. Neither blocks the
independent lifecycle and suggestion/confirmation UI source preparation.

## UK minimal version observation proposal — NOT EXECUTED / requires root review

Reuse 322 observation: HTTP200/READY proves PROCESS_AND_DATABASE_CONNECTIVITY
only. runtime_source_sha/version_source/freshness/backend_observed_at UNKNOWN;
current_container HOLD_UNKNOWN/current_image NOT_OBSERVED. Do not infer its cause.
Historical resume source 2330 and rollback are historical, not current version.

A minimal next observation can split container ID from complex command/mount
comparisons. Use the exact original bounded capture/safe_file/project_container/
project_image primitives from community_preview_version_inspect.py, under the
same original host-root guard, protected Docker executable/socket, 60-second total
budget, <=64KiB child output, <=16KiB final typed JSON. No raw stderr or inspect
JSON may be relayed. Do not execute this proposal before independent review.

1. Fixed read-only command array: `/usr/bin/docker --host unix:///var/run/docker.sock
   container inspect --format <base_template()> xuanjun-community-preview`.
   base_template returns only typed .Id/.Image/.State.Running/.Config.User.
   Use project_container(raw), without complex Entrypoint/Cmd/mount comparisons.
   A failed/unsupported command remains HOLD_UNKNOWN, never substitute rollback.
2. Only after observed valid current image ID, fixed `image inspect --format`
   selects .Id/.RepoDigests/org.opencontainers.image.revision/.Config.User. Bind
   project_image(raw, observed_image_id). No Env, arbitrary labels or full JSON.
3. Repeat step1 and require unchanged container+image+running. Report non-atomic
   observation if it changes. Image ID and repository digest remain separate.
4. OCI revision can establish the image revision only. Because runtime health
   lacks actual version/freshness, runtime/preview same-version remains HOLD.
   No `docker exec`, container filesystem, Env, DB body, P2 runtime/data, service
   mutation, old fixed upgrader, deployment or preview/upload is in this proposal.

If the minimal inspect still fails, a separately reviewed fixed exit-status/error
classification is needed; do not expose arbitrary stderr or expand scope by trial.
No shell command or inspector has been executed against UK by this Writer.
