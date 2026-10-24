# PR17 B5 successor source candidate

Status: DRAFT, DEFAULT CLOSED. No UK execution, approval, source transfer, or
installation follows from these files.

The 22,830-byte original reviewed specification remains intact as
`ORIGINAL_REVIEWED_SPEC.json`. `SUCCESSOR_SPEC.json` is a distinct 17-stage
candidate for the 42-path f0fe runtime. The old 32-path c53 binder cannot
authorize this version. `SUCCESSOR_CONTROLLER_SOURCE_MANIFEST.json` records
the source bytes in this candidate. The new release gate checks a separately
approved binder SHA, all controller source bytes, and both current targets
again at preflight, publish, start and recover. The external binder data
points to controller commit `2875cb3761edcabfac0ca09bef2d3c441ae53521`
and is a source identity candidate only. Its independently protected approval
pin and production reader have not been issued. Default-off protected record
consumers exist, but no real UK registration has occurred. The factory uses the matching
successor runtime and Transaction. A recovered custody checkpoint restores
only the read-only B5 HTTP wait; original tool provenance and separate close
approval remain mandatory for the original scoped close path.

| Stage | Candidate source | Boundary |
| --- | --- | --- |
| Spec | `successor_contract.py` | Exact 17 stages, 19 objects and 93,592 bytes; draft only. |
| Publish | `successor_controller/pr17_b5_successor_backend.py` | 42 fixed source paths and manifest, no overwrite; six protected config/slot changes remain under the original lock and CAS. |
| Maintenance | `successor_controller/pr17_b5_successor_local.py`, `pr17_b5_successor_review.py`, `pr17_b5_successor_runtime.py` | Owner/B5 batch witnesses, original queue, stop, release, start, window, intake and custody are separate checkpoints. No bearer copied to maintenance. |
| Read | `successor_analyst_read.py` | B5's request-local cloud read validates each original response and whole SHA. A callable fixture proves bytes, not tool provenance or a real files grant. |
| Close | `pr17_b5_successor_review.py` | Requires a trusted B5 HTTP provenance record and separate precise close approval. These producer interfaces are unbound and remain HOLD. |
| Recovery | `pr17_b5_successor_backend.py`, `pr17_b5_successor_review.py` | Protected intent/SENT and original file-backed Queue reconcile in a new process without repeating POST. A completed custody checkpoint restores only the wait for B5 HTTP provenance; unknown custody and mutations remain HOLD. |

No live caller supplies the new gate's independently approved binder digest,
protected source reader and link observations. The original protected six paths, two
current links, queue identity, original maintenance/restore/close scopes and
per-request files grant require actual protected observations. Source freshness
also remains unproved: A5 refers to the retained archive, and L14 to the
previous installed paths. Neither a catalog date nor a receiving directory
proves those sources still exist. The 19 bodies have not been read.

Before any new batch, the original operator must bind the actual release
commit, this controller manifest, the reviewed successor spec, original source
identities, exact witnesses and grant, and the protected producer for precise
restore/close decisions. The B5 analyst must independently receive all 19
original cloud responses with a real request-local `project.files.read`
authorization and verify 93,592 bytes against the frozen objects. A synthetic
test or a hash supplied by the caller cannot substitute for either fact.

## Exact remaining producer contracts

| Source | Minimum non-secret bound facts | Current consumer and state |
| --- | --- | --- |
| Original UK maintenance enrollment and protected file reader | Independently approved SHA of the freshly frozen external binder, controller commit, 12 source records, both `current` targets and installed 42-file runtime trees, exact batch/job/attempt, validity and revocation. | Default-off `SuccessorEvidenceStore.register_exact('release')` publishes a fixed root-protected record; `ExternalReleaseGate.from_registered` reads it, and `check` re-reads it at preflight/publish/start/recover. Production preflight checks that the authority and gate use the same binding. The trusted UK registrar and actual protected source readers are **not yet enrolled**. A generated binder or fixture SHA cannot register itself. |
| Original UK scoped decision registrar | Separate original source ID/content digest, witness identity, job/batch/attempt/19 IDs/catalog, scope, phase, validity and revocation for `PRE_START_RESTORE` and `B5_EXPOSURE_CLOSE`. | `ExistingRequestAuthority` consumes the fixed records; restore/close actions hold a shared scope lock until the bounded action ends, while completed revocation excludes new actions. No live original decision or registrar has been supplied; absent record still HOLD. Maintenance approval cannot fill either record. |
| Original B5 request-local cloud tool and UK coordinator | B5's actual 19 `read_project_chunk` result references, original InvokeIds, per-item SHA/bytes, custody digest, authenticated subject/recipient and `project.files.read` scope; coordinator checks the original results and registers only non-secret metadata. | `successor_analyst_read.receive_all` verifies actual response bytes. A separate fixed `b5_http` UK witness binds its proof digest and 19 rows; `verify_b5_http_provenance` consumes it under the revocation lock before close. This is **human witness custody**, not a tool signature or an automatic authentication chain. Neither B5's real results nor the trusted coordinator registration exists yet; live per-request files grant remains necessary. |
| Original UK source custodian | Current A5 archive and L14 installed file identity, path, owner, size and SHA, with no substitution of historical A5 by live L14. | Source freshness before new batch UNKNOWN; neither this repository commit nor a catalog date proves it. |

The current controller source commit is
`2875cb3761edcabfac0ca09bef2d3c441ae53521`, the manifest SHA256 is
`9d0d615bc4ecd949170f0ce5132070cef3ed82690890d560e8d7cc59593316fa`,
and the 1,011-byte external binder SHA256 is
`684e39b01e0248b1f28b64d6dabbf31fcdd0cebda0dbc36bb0518e068369641b`.
The binder file only describes code identity. Its SHA in this document or a
test is not a production approval. The normal OAuth tool's definition does
not prove that 19 SUCCESS jobs, custody, or live files grant exist.

The proposed fixed UK evidence root is
`/var/lib/xuanjun-cloud-connection/b5-new19-successor-evidence-staged-f0fe0d3978b7`.
Production registration is disabled by default and requires the original UK
Workbench plus sudo identity, an independently reviewed original source, a
pre-existing root-owned `0700` directory and `0600` `register.lock`. The only
non-overwriting output names are `release.json`, `restore.json`, `close.json`,
`b5-http.json` and `revoked.json` (each root-owned `0600`); interrupted
`.pending` files cause HOLD. No directory, permission, approval record, grant,
or tool result was created on the UK host by this candidate. The registrar
identity, original approval sources and B5 result references are site facts
to establish separately before any stage admission.
