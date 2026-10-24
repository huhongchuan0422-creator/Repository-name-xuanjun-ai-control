# B5 fixed 19 offline candidate

This directory binds the reader delta to the previously reviewed source
bytes. `SOURCE_MANIFEST.json` records each logical release path, its bundle
path, size, and SHA-256. The original 32 source files came from the pinned
source archive; the four local release overrides and original B5 helpers are
separate entries. It is a draft source review unit, **not** a production
release or permission to activate the new batch.

The targeted tests run directly from this directory:

```
python -B test_old_policy_dependency_reader.py -v
python -B test_original_capability_preflight.py -v
python -B test_canonical_prestart_proof.py -v
```

The prestart observation A authenticates the original database pin, enforces
aggregate size and row bounds before returning request bodies to Python, and
uses a monotonic deadline and SQLite progress handler. It returns HOLD before
connecting to a live WAL database because SQLite read markers can modify its
SHM file even in read-only mode. The locked observation B independently reads
the complete bounded set after the worker has exited and the original lock
and database FD have been proven.

The original maintenance caller, deployment identity and permissions, grant,
new batch acknowledgements, 19 bodies, original custody, live WAL coordination,
independent review, and installation are not established by this commit. In
particular the earlier runtime code pin and release manifest cannot be reused
for these changed bytes. A reviewed complete release and external binder must
be generated only from the final exact source and actual commit identity.

## Complete chain boundary for this draft

| Step | Existing entry | Current outcome |
| --- | --- | --- |
| Prestart | `ExistingRequestAuthority.preflight_original_capabilities` → A reader | Fixed source and DB pin; live WAL returns HOLD before SQLite connection. |
| Reservation/activation | `Transaction.execute` → original backend CAS, lock and checkpoint | No live six-slot, two-current or original DB evidence in this candidate. |
| Intake | `OriginalComposition.send_once` → durable intent → original `Github.call` or enrolled publisher → original Queue READY | No enrolled production maintenance caller or authenticated publisher in this candidate. SENT and UNKNOWN must never be posted again. |
| Success/custody/body | original Queue `bound_job`, Receiver custody, `OAuthProjectResource.read` | Requires 19 real SUCCESS/InvokeId, current files grant and request-local Authorization; fixture evidence does not supply them. |
| Close/restore | exact job approval → stop → observer release → lock/DBFD → fixed close or precise restore | The original authority's `approve_precise_pre_start_restore` and `approve_c53_b5_exposure_close` still HOLD; maintenance witness does not authorize those scopes. |

The only source-local fixes in this revision are final scan-deadline checks,
fixed-job journal read scope, and detaching/closing the owned observer before
closeout reopens the original DB. A failed observer close is UNKNOWN. No
production approval source, token transfer, second transport or grant was
created. The original `oauth_http.create_resource_app` has request-local
Authorization, but this candidate has no registered caller that conveys that
request context to the maintenance process. The old c53 release constant and
pin cannot authorize these new bytes. Freeze a new binder only after a full
source review and the actual release commit; the fixed 19 SUCCESS results are
post-start observations, never a prerequisite for prestart admission.

## Staged original route and exact provenance

`prepare_maintenance_candidate` now constructs the original `Github`, `Cloud`
and shared `Network` from the frozen bundle when the caller supplies a real
request-local Authorization accessor; absent one, the maintenance accessor
explicitly refuses the body action. Recovery reconstructs the same provider
types. Construction performs no POST, token read or approval. The maintenance
process has no analyst request context. The original resource HTTP `oauth_http.mcp` authenticates
each `read_project_chunk` call with `project.files.read` and the catalog project;
this is the legitimate final hop after custody, outside the maintenance process.

| Stage | Code entry and original evidence | Boundary |
| --- | --- | --- |
| Admission | `Transaction.execute` → `ExistingRequestAuthority.preflight_original_capabilities` → A old-policy observation, receiver conflict and exact Owner/B5 witness | Current old binding, protected queue and two distinct same-batch receipts required. Live WAL A still HOLD. |
| Reservation/change | `R2HostBackend.reserve_batch_and_targets`, stop, lock, B reobservation, six protected backup/CAS, two releases, start | Original lock, DB identity, current slots and old Invoke history rechecked. No 19 SUCCESS prerequisite. |
| Intake | `Transaction.run_19_after_window` → backend `submit_original_intake_once` → `OriginalComposition.send_once` → `Github.call('/issues/17/comments')` | Fixed actor/response, fsynced intent before POST, SENT is not READY; unknown response never reposted. Original worker Queue produces READY. |
| Result/custody | `observe_original_success_progress`/`verify_original_success_receipts` → original `bound_job`; `custody_once_authenticated` → original Receiver | Nineteen actual SUCCESS Invoke IDs, catalog/recipient/size/SHA and custody receipt. |
| Analyst body | Original authenticated HTTP `oauth_http.mcp` → `OAuthProjectResource.read` → `read_project_chunk` | Each new request authenticates live `project.files.read`; 19 bytes and SHA verified. Maintenance has no bearer handoff. |
| Restore/close | exact scoped original approval → guarded backend original history and stop/close | The two exact scoped producers remain UNKNOWN; no maintenance approval can stand in. |

`freeze_runtime_source.py` verifies every `SOURCE_MANIFEST.json` source byte,
then emits a standalone `RUNTIME_SOURCE_MANIFEST.json` for all release paths.
This inventory is independent of its own bytes. Once the complete source is
committed and reviewed, `--commit <actual HEAD>` emits an *external* binder
containing the real commit/tree, runtime manifest SHA and original nine-file
worker code pin. It refuses a dirty tree or a mismatched HEAD. Neither this
inventory nor the external binder changes the c53 spec, old code pin, or any
protected deployment slot. A separate reviewed successor spec and exact
site admission remain necessary; the old c53 pin cannot install this draft.
