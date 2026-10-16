# Fixed capability-lifecycle preparation candidate

Local implementation and synthetic regression only. No production invocation, host inspection, review publication, admission, claim, or recovery phase has been performed. New source commit, source tree, kit manifest, entry SHA256, and entry size remain `None`. `prepare` refuses at that binding gate before any host read. Binding and publication require a separately reviewed immutable artifact; the tool provides no path or pin overrides.

## Actual preparation path

The standalone `epoch7_prepare_successor.py` implements the fixed preparation path. Its only operations are `input-contract` and `prepare`; preparation takes one explicit `admission_expires_at_utc` value. It accepts no approval ID or approval-body signature and cannot manufacture approval.

1. Require the fixed root host and isolated/no-site/no-bytecode interpreter. Initialize the frozen cold UUID parser with optional ctypes discovery blocked. Authenticate both selected entry files through retained no-follow descriptors, then authenticate their complete kits. The old resourcebind manifest is `6c269db1…`; its source remains `ef21ca95…` / tree `5a70c562…`. The target is the fixed sibling `epoch7-recovery-candidate-r7-claim-lifecycle`.
2. Read the three original private inputs at their fixed root:root/0600/nlink1 paths. Exact lengths and full SHA256 pins are retained in source: seed 769086 / `6de7d122…`, plan 140648 / `eae1e341…`, packet 20089 / `c762ecdd…`. Reproduce the original plan and proposed body with the original kit's real factory. The existing old review is inherited evidence only. The original a560… predecessor remains the required receipt; the failed prior successor attempt supplies no renewed authority.
3. Use the authenticated target kit's real `DescriptorReader` to read and validate the fixed predecessor bytes, file metadata, all protected ancestors, and old-inner/new-outer/new-inner absence. Enumerate the entire transaction through the loader's real retained-descriptor inventory; hash every original file and compare the exact original inventory plus the predecessor. Preserve historical directory rows, accepting only the fixed transaction parent's size/mtime_ns/ctime_ns change. Freshly reject extended ACLs and capabilities. The comparison proves a finite relation, not the cause of timestamp changes.
4. `compile_successor_bundle(verified_new_kit, original_private, measured, admission_expires_at_utc)` is the pure new-loader contract. The caller must own authenticated imports, original-input authentication, actual descriptor measurement, and final rereads. The helper validates the finite proof relation; deep-copies the unchanged original private fields; adds the schema-1 `claim_successor` with exact `timing_policy=PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1`; then calls the real `_hydrate_seed`, `prepare_host_inputs`, `compile_host_contract`, and `expected_complete_from_inputs`. It serializes schema-2 seed, new plan, and an unsigned review packet. Full new implementation identity, exact expiry, fresh measured-proof digest, old record/binding/state/input/review identity, fixed journal names, one successor, and no automatic retry are bound. No process-local admission capability is created. The signed timing policy selects atomic prepared-handle consumption within its original 30 seconds, all independently bounded ordered guards, and a later one-use publication capability capped by mint+30 seconds, the running final-inner-guard deadline, and the immutable prepare-time UTC-to-monotonic ceiling. The current signed UTC bound remains independently required. This preparation wrapper does not execute that lifecycle.
5. Reauthenticate both kits, exact original bytes and metadata, and the complete predecessor measurement before publication and again afterward. Publish exactly three new content-addressed private files under the fixed candidate parent using the existing O_EXCL/no-follow/0600 write/fsync/readback mechanics. The fixed prefixes are `epoch7-lifecycle-approved-plan-`, `epoch7-lifecycle-resume-inputs-`, and `epoch7-lifecycle-review-packet-`; the first two match the schema-2 loader. There is no overwrite or removal path.

Original files, observation, saved seed/plan, and review packet are never rewritten. All 107 runtime payloads must remain byte-identical between selected old/new kits. Original factory validation remains present. Its fixed database/socket `realpath` checks may read filesystem metadata; preparation is not represented as touching only the three private inputs and predecessor. No process census, SQL query, probe execution, command launch, lock acquisition, driver assembly, external fetch, or production phase is invoked by this wrapper.

## Failure and remaining gates

The budget is a one-shot alarm plus terminal monotonic check. Errors or interruptions retain every partial output, include confirmed outputs and known created paths, never retry a write, and never delete or adopt partial files. Existing any output refuses the whole publication before writes. A status failure after successful creation carries all output metadata; cleanup uncertainty is reported independently. Absence after an interrupted create cannot prove that no attempt occurred. The tool is preparation only; produced bytes do not grant install or successor admission.

Actual host/source provenance, real fixed 1641-byte predecessor authentication, source publication, new exact review, and execution remain separate gates. The selected target pins remain unbound in this source. Admission expiry is prospective, and cannot be used to suppress independently authorized containment/receipt preservation after a later attempted/admitted transaction.

## Focused local verification

`test_prepare_successor.py` is the sole preparation suite. It imports only fixture definitions from the already present candidate tests/baseline; it does not discover or run old suites. It uses `tests/synthetic_historical_seed.py`, explicitly completes that fixture's missing archival transaction-directory/inventory rows, and reconstructs its synthetic probe hash closure. No historical production observation is changed. Missing, old, or malformed timing policy is rejected by the real new-loader hydration path, while the exact policy propagates through the generated seed, unsigned review body, and hashed plan contract.

The real lifecycle factory, all 107 payloads, 17 resource views, schema-2 loader hydration, plan/body serialization, and exclusive private writer run. The descriptor measurement tests run the actual no-follow reader and inventory against a temporary filesystem; only namespace/root ownership and immutable predecessor-byte pins are synthetic. A separate negative proves the unchanged real predecessor pin rejects the synthetic receipt. Source identities and proposed future timestamps in tests are fixtures, not public bindings or approval.

Local coverage includes original field preservation, schema-2 roundtrip, proof/source/manifest/expiry propagation, missing expiry/unbound pins, fixed absence requirements, inventory/ancestry drift, real predecessor final rereads, private modes/symlinks, existing-output rejection, first/second-write interruption, failed readback, final output drift, status failure retention, cleanup uncertainty, and one-shot timer cleanup. The broader candidate's Python3.6 limitation remains separately reported; this preparation suite does not repair it by preloading imports or weakening gates.

The focused preparation suite passes all 30 cases on Python 3.12.14 with `-I -B -S` against the updated lifecycle core (local log: `test-lifecycle-python312.log`). No historical test suite was discovered or run. This is source-level local regression evidence; final immutable artifact binding, complete Python 3.6 verification, host provenance, and independent review remain separate gates. Two composed `prepare()` cases exercise the real compiler, private-input descriptor reads, entry-file rereads, three-output publisher, and final output checks; immutable source authentication and host proof are explicitly synthetic boundaries. The post-publication proof-drift case verifies all three outputs remain present and reported.

One isolated Python 3.6.8 suite invocation was attempted with core dumps disabled.
It exited 1: 19 tests ran and two class setup errors occurred because each original
synthetic seed subprocess died with SIGSEGV 11. The real compiler/hydration
composition groups did not complete. Their Python 3.6 coverage remains UNKNOWN,
with no diagnosis, retry, frame-identity claim, or gate relaxation. Evidence is in
`test-lifecycle-python368.log` and `test-lifecycle-python368-exits.json`.

## Composed fixture namespace boundary

The exact-HEAD rehearsal previously reported `final_read -> recheck -> PATH_IDENTITY`;
the log did not identify which directory changed. Ambient temporary-directory
contention is a hypothesis, not a measured cause. The composed tests now map logical
`/` to a private temporary anchor with actual `parent/candidate` descendants. Only
the preparer and isolated test entry module receive a test-local OS proxy; shared
stdlib OS functions are never changed. Absolute open/stat paths resolve inside the
anchor, and relative dir_fd calls remain unchanged. Original open_chain, directory
authority, recheck, DescriptorTree, readback, publication and partial-output retention
logic run over three distinct actual ancestor FDs. The namespace excludes physical
ancestors above that private anchor, including shared `/tmp` when used by CI.

Existing cases explicitly reject mutations of the anchor, parent and candidate,
and a symlinked candidate path. The standalone private-reader case also exercises
original open_chain/recheck without namespace mapping. The two composed cases still
verify successful three-output publication and post-publication proof-drift retention.
No production source changed; case inventory remains 30.
