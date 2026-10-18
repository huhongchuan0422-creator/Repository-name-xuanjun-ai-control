# R14 versioned full acceptance

This is an additive acceptance version for the exact R1-R4 source candidate.
It does not edit, rename, disable, replace or turn green the historical full gate.
No protected required-check configuration changes are made. The old failed run
39087808348 and later executions of that gate retain their actual conclusions.

`VERSION_DIFF.json` records the four changed files that collide with historical
literal SHA/length pins, plus the old/new Kit source and Manifest/build-result
identities. Additional R14 source/test files also fall outside the old allowlist.
The old gate binds source105996ed / Manifest91252ba7; the current published Kit
binds source0bd83e6f / Manifest1fd0056e. Treating the old gate as a new-version
receipt would be incorrect. Original gate files and fixed-version assertions are
preserved byte for byte.

## Complete exact-checkout evidence

INPUTS.json pins the full candidate file allowlist, every byte length/SHA,
all selected archived dependencies, both gate sources, both workflows and the
historical source objects used by the unchanged tests. The manifest itself and
each selected file must match the actual Git HEAD; current Commit/Tree are
recorded from that exact checkout. No path/pin override is accepted. Symlinks,
hardlinks, changed bytes, unlisted files or post-test drift cause failure.

The exact published v2 archive, all257 contents/256 pins, module index/static
import closure, inherited test imports,107 runtime payloads and16 business phases
are verified. The original approved builder rebuilds it twice from immutable
source0bd83e6f/tree5d790e58 and checks every selected input against that Git tree.
All rebuilt contents and complete build metadata must match the separately bound
EXPECTED_BUILD_RESULT.json. Only gzip byte count/hash may vary across native
Python versions; decompressed contents/Manifest/source identity may not vary.

## Test coverage

| Scope | Count | Source under test |
|---|---:|---|
| Current related full suites | 325 | Current candidate; versioned31/47 Preparer/Delivery ports |
| Unchanged historical related suites | 325 | Separate exact0bd83e6f source fixture |
| Original adapter boundary contracts | 55 | Unchanged historical gate utility implementation |
| Historical approval tests | 18 | Authenticated baseline helper/test bytes |
| Current approval author positive/negative tests | 20 | Actual current approval helper, hash-checked before import |
| New gate contract negatives | 15 | New versioned gate |
| R1-R4 real download-to-Prepare E2E | 17 | Actual current implementation, synthetic private/host boundaries |
| Total, no skips permitted | 775 | Distinct actual results, not wrapper counts |

The new Preparer/Delivery ports are separate named files. They retain every test
name/count from the historical originals and update only the new binding/path
expectations and their local fixture layouts. Original assertions still run in
the separate historical fixture and also remain in the unchanged historical CI.
No implementation is patched to satisfy an old constant. Current325 tests run
against current source; historical325 results never stand in for current results.

The original historical outer rebuild mismatch is not reclassified or suppressed:
it remains visible in its original workflow. This new gate performs its own
complete exact-source reconstruction against the correctly bound current Kit.

All fixture processes execute in newly created protected local namespaces. No
UK Root, production Prepare, install, claim, service, rollback, private real input
or approval-signing action is performed. P2_RELEASE remains HOLD. The existing
five-attempt policy is not implemented by this CI-only change.

Run with isolated native Python:

`python3 -I -B -S full-ci-v2/verify_full.py --output <new-local-output-directory>`

The output must not exist. FULL_RESULT.json and the evidence archive record the
actual current Commit/Tree, full file SHA set, per-suite/log results, dependency
identities and artifact SHA. Hosted3.6.15 and3.12 must both finish successfully
before the consolidated PR58 incremental review request is submitted.
