# B aggregate boundary failure: exact diagnosis and local repair

## Actual attempt

The received terminal attachment is 9,791 bytes, SHA256 `d8c885a247beb6736312a986fccf7a4b934c36ed4833d29f00ce1487901e6318`. It reports compiler `EXTRACTED_AND_VERIFIED`, preparer `STAGED_EXACT`, no created private output paths, no completed outputs, and `cleanup_unknown=false`. The terminal itself remains private.

The authenticated call chain reaches factory `_proposal`'s complete resource-view comparison, then `epoch7_delta.same` → `canonical` → `need` at lines 94 → 85 → 79. The exact failed condition is `len(canonical_json) <= 2,097,152`; its static label is `PROPOSAL_SIZE_BOUND`. This is a canonical aggregate size failure, not another missing parent key. The captured traceback does not separately identify the resource-views versus resource-directories operand or comparison side. Exact real object sizes were not retained and remain UNKNOWN.

The actual path already crossed fresh-parent validation, source-derived access rows, both complete service-contract validations, and construction of all 17 resource views. It also crossed the checkpoint compiler: each of 17 × 15 section row lists passed its existing 2MiB digest bound and finite row checks. This establishes the old parent omission was passed during this attempt; it does not claim the later final fresh checks or private publication occurred.

## Root cause and prior fixture limitation

The resource planner deep-copies the complete preserved resource set into every checkpoint. The factory already has a typed segmented input digest, but still applied the generic 2MiB proposal canonicalizer to the entire repeated view set. Three later consumers did the same, including C construction and every mutation recheck. Fixing only the failing comparison would leave the later B/C failures in place.

The earlier full-factory fixture used just one historical payload in each historical release. It therefore tested the real current 107-file compilers but did not cover the preserved production release inventory volume. The new fixture has three synthetic historical releases with 102 payload records and 48 realistic cache records each. It is explicitly synthetic historical/host data, not the original private observation.

## One shared bounded binding

New helpers in `epoch7_resource_observer.py`:

- `resource_views_digest`: validates exactly 17 checkpoints, exact 15 section names, ordered lists of 1..8192 unique canonical paths; retains `delta.digest(rows)` and its original 2MiB boundary for every section. The versioned outer envelope binds checkpoint index, section name, row count and every section digest. It never serializes the complete repeated aggregate as one proposal.
- `same_resource_views`: exact canonical equality separately for every section, after validating both structures. No row is dropped or replaced by an unverified claim.
- `resource_directories_digest`: validates the existing finite directory structure, hashes each real path together with its complete ordered states, and hashes a versioned outer list of at most8192 leaf hashes. Long original paths remain inside their bounded leaf; they cannot blow up the outer list.
- `same_resource_directories`: exact key set plus exact per-path canonical equality.

All consumers are changed together: factory source-derived comparisons and plan hashes; `CheckpointResources` construction and mutation guard; host observer initial plan bind and ongoing directory binding. Original `ResourceReader` permission/type/ACL/race checks remain present. Global `epoch7_delta.canonical` is unchanged and still rejects an ordinary object above2MiB. Existing per-section hash contracts and all evidence rows remain unchanged.

The separate diagnostic overlay adds the exact `PROPOSAL_SIZE_BOUND` code and static labels from the three already authenticated compiler sources. It emits no free-form error text. Existing error-output fields, partial-write retention and output budgets are unchanged. Its `PINS_BOUND=False` explicitly prevents use as a new delivery.

## Focused closure evidence

The new large fixture reproduces the old aggregate-bound rejection. With the changed helper chain it produces:

- aggregate resource views:3,325,808 bytes;
- largest section:150,776 bytes;
- plan:140,247 bytes, below2MiB;
- private seed:337,692 bytes, below64MiB;
- review packet:8,241 bytes, below2MiB.

New tests exercise real factory preparation and compilation, wrapper serialization, actual three-file exclusive publication/readback, target entry seed hydration, same-plan recomputation, and real C checkpoint/host-observer bind and mutation guards. Host reads/effects remain inert synthetic boundaries. No C installation or actual UK run is claimed.

Negative coverage includes missing/extra/reordered checkpoints/sections/rows, changed late-row values/types, old flat digest rejection, leaf and row-count bounds, directory keys and maximum-size outer envelope, post-bind mutation, wrong target root, output collision, static error label privacy, and required independent C review. The affected older observer-binding fixture now uses valid ordered resource rows and valid directory states instead of scalar markers/empty directory states.

## Version and remaining gates

The new compiler consumer root is `epoch7-recovery-candidate-r7-resourcebind`; the new preparer root is `epoch7-preparation-candidate-r7-resourcebind`. The already staged `r7-parentfix` compiler and `r7-fresh-parent` preparer are not overwritten. Original A observation, kit, review body and saved proof remain unchanged. The new preparation overlay's separate compiler manifest/entry pins are deliberately `None` pending an immutable rebuilt compiler artifact. No new command is generated.

Necessary next integration is an explicit new compiler manifest/artifact binding and corresponding delivery/CI pins after local review and authorized publication; old compiler bytes cannot be relabeled. The current107 runtime payloads are unchanged. Future C still needs its complete independent approval.

No extra Owner measurement is needed to establish or repair this proven source-level aggregate defect. The current receipt cannot provide exact original aggregate sizes or new parent tuples. A separate diagnostic should be considered only if a remaining claim genuinely requires those private actual values; it must not be used to test the next known compiler failure on the Owner's host. Race/authority refusal during a future authorized B attempt remains legitimate and cannot be promised away by local fixtures.

## Exact package and tests

The new offline builder starts from the exact published parentfix archive, SHA256 `6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307`, and manifest `b33b365ef1fd18458d85bcbbec44d883f3cc33bf859064cbdca6bfc3fad7d571`. Its eight input rows replace six files and add two authenticated test files. The result has 255 cache pins, 256 regular files and 42 directories. All 107 runtime payloads and all 110 runtime package files are byte-identical. `modules` and `test_suites` are unchanged. The aggregate fixture has a non-test import alias, so the new 25 cases run through the exact public CI harness; they are not claimed as automatic `VerifiedKit.tests` coverage.

Local Python3.12.14 results: 25 aggregate +12 diagnostic/version +6 affected observer +32 builder; the same 75 cases pass inside the committed disposable checkout. The 45 CI boundary cases and two top-level gate cases pass, with exact source hashes/HEAD checked before and after. Independent review separately reproduced 25+12+6+32. Hosted and official Python3.6 runtime results are pending publication; local 3.6 evidence is native compile-only for the 17 public Python files.

The first CI rehearsal reached 75 passing cases but its archive output exceeded an inherited 1MiB file limit. The correction gives only the builder child a finite 32MiB file limit, while every child's stdout remains bounded to 1MiB and ordinary suite children keep the 1MiB file limit. Owned-session cleanup and deadlines remain. The initial failure is preserved locally; no production proposal limit changed.

The publication scope has exactly 29 unique repository paths: 22 initial source/CI/metadata files and seven later artifact/binding/delivery additions. Actual source commit/tree, selected archive and final wrapper/delivery pins require immutable publication. Synthetic all-zero build identities and temporary local Git identities are not production pins. No executable retry command is included. The current delivery overlay is diagnostic-only with `PINS_BOUND=False`; final root/archive/source pin integration is still required.

## Reproduction

The top-level public gate materializes only exact hash-bound public source dependencies and the two existing archives, then runs the focused suites in owned, bounded child processes. Run `tests/test_p2_b_resource_aggregate_fix_contract.py` and `tests/test_p2_b_resource_aggregate_fix.py` from an exact committed public checkout. Builder CLI flags are `--archive`, `--candidate-root`, `--overlay-map`, `--source-commit`, `--source-tree`, `--output`, and `--metadata`. Actual commit/tree identity is supplied and independently verified by the caller; the builder has no Git/network authority.

A test-only Python3.12 restriction discovered before publication was removed. On Python3.6 the grammar check uses the native parser; newer Python explicitly selects 3.6 grammar. The same 32 builder cases remain mandatory on both Hosted interpreters, with no skip or environment-based bypass.
