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
points to controller commit `1068f49acf8c6052e3f9774c38fa3585a45dbfce`
and is a source identity candidate only. Its independently protected approval
pin and production reader have not been issued.

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
| Original UK maintenance enrollment and protected file reader | Approved SHA of `EXTERNAL_SUCCESSOR_DEPLOYMENT_BINDER.json`, controller commit, 12 source records, fixed source root, both `current` link identities and both installed 42-file runtime trees, batch/job, validity and revocation. The source file is 1,012 bytes with SHA256 `6408c24bd76492c865b0ac0677877c2748d74095759ea82c1a334f94928ea5e9`. | `ExternalReleaseGate.check` is called at preflight, publish, start and recover. `prepare_local_adapter` and `reconstruct_recovery_candidate` accept only an explicitly supplied gate. No enrolled protected digest/reader currently constructs it; HOLD. |
| Original UK scoped decision registrar | Independent exact job, batch, attempt, actor, source ID, valid-until and revocation for pre-start restore and post-B5 close, each with its own scope. Maintenance approval alone cannot satisfy either. | `ExistingRequestAuthority.approve_precise_pre_start_restore` and `approve_c53_b5_exposure_close` remain HOLD. |
| Original B5 request-local cloud tool | Authenticated invocation provenance bound to 19 request IDs, catalog, recipient, original InvokeIds, custody receipt, per-item and total SHA/bytes; active `project.files.read` checked on each call. | `successor_analyst_read.receive_all` verifies response bytes. `verify_b5_http_provenance` refuses the caller-supplied hash and keeps close HOLD until an original authenticated provenance reader exists. |
| Original UK source custodian | Current A5 archive and L14 installed file identity, path, owner, size and SHA, with no substitution of historical A5 by live L14. | Source freshness before new batch UNKNOWN; neither this repository commit nor a catalog date proves it. |

The binder file only describes code identity. Its SHA in this document or a
test is not a production approval. The normal OAuth tool's definition does
not prove that 19 SUCCESS jobs, custody, or live files grant exist.
