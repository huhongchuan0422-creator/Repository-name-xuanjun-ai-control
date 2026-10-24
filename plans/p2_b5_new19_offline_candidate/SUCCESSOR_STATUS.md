# PR17 B5 successor source candidate

Status: DRAFT, DEFAULT CLOSED. No UK execution, approval, source transfer, or
installation follows from these files.

The 22,830-byte original reviewed specification remains intact as
`ORIGINAL_REVIEWED_SPEC.json`. `SUCCESSOR_SPEC.json` is a distinct 17-stage
candidate for the 42-path f0fe runtime. The old 32-path c53 binder cannot
authorize this version. `SUCCESSOR_CONTROLLER_SOURCE_MANIFEST.json` records
the source bytes in this candidate; an independent deployment binder for the
**actual commit containing these files** has not been issued or consumed.

| Stage | Candidate source | Boundary |
| --- | --- | --- |
| Spec | `successor_contract.py` | Exact 17 stages, 19 objects and 93,592 bytes; draft only. |
| Publish | `successor_controller/pr17_b5_successor_backend.py` | 42 fixed source paths and manifest, no overwrite; six protected config/slot changes remain under the original lock and CAS. |
| Maintenance | `successor_controller/pr17_b5_successor_local.py`, `pr17_b5_successor_review.py`, `pr17_b5_successor_runtime.py` | Owner/B5 batch witnesses, original queue, stop, release, start, window, intake and custody are separate checkpoints. No bearer copied to maintenance. |
| Read | `successor_analyst_read.py` | B5's request-local cloud read validates each original response and whole SHA. A callable fixture proves bytes, not tool provenance or a real files grant. |
| Close | `pr17_b5_successor_review.py` | Requires a trusted B5 HTTP provenance record and separate precise close approval. These producer interfaces are unbound and remain HOLD. |
| Recovery | `pr17_b5_successor_backend.py` | Protected intent/SENT observations in a new process do not repeat POST; uncertain custody and mutations remain HOLD. |

No live caller is wired to the new controller manifest or an external binder
for this candidate's final commit. The original protected six paths, two
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
