# Preparation delivery with safe failure projection

This new local candidate targets the fresh production leaf
`epoch7-preparation-candidate-r6-contracts`. The existing r5/r6 directories and
reviewed delivery/diagnostic candidates are preserved. The recovery kit remains
`epoch7-recovery-candidate-r6`.

## Scope and bindings

The only operation is exclusive staging of exactly three preparation files,
followed by `propose-topology` and read-only verification of the staged inventory.
A new directory is 0700 and each source file is 0600. An existing complete exact
inventory may be reused. Partial or uncertain creation is retained and reported;
there is no overwrite, repair, cleanup retry, install, resume, approval, or
private-plan compilation through this endpoint.

The source hashes identify the repaired preparation wrapper and unchanged data
and topology modules. The wrapper still performs the preparation path's eight
case, receipt, Node proof, peer identity, SDK binding, namespace/readpath,
posture, and expected-denial checks. This delivery change does not replace or
relax those checks. Local tests do not establish their success on the real host.

The genuine observation binding is unchanged: suffix
`epoch7-observation-1311b9e9fa97cfd4.private.json`, SHA-256
`b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246`.
No private observation or receipt bytes are included in this candidate.

`PINS_BOUND=True` and `PUBLICATION_COMMIT` is the actual reviewed preparation
publication `8ab751a84922b76b80c8e8641cbe96e82fa5d391`. The root publisher reports
that preparation tree `57229d7cb6a47fc3329badd9653c4cc6e377ea23` and all ten
published blobs were fully read back and matched. This local worker performed no
Git or network operation. The preparation prefix is
`evidence/p2-epoch7-access-repair-20261014/preparation-source-r6-contracts/`.

The owner template's three own-delivery-publication fields remain unset, so the
template is not ready to run and rejects before host or network access. Its
neutral first comment does not need to change during later pin-only binding.
The delivery prefix is
`evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r6-contracts/`.
No delivery publication commit, topology review, or approval has been invented.

The prior unbound checkpoint is preserved. The only helper-source changes from
that reviewed checkpoint are the two preparation-publication assignments above.
The main binding regression now expects the actual publication; the separate
explicit `PINS_BOUND=False` pre-effects negative test is unchanged.

## Safe diagnostics

The frozen diagnostic source SHA-256
`9cd065c6fb7d7f756314420d0867d4f639fcef090d82b449fdc3a20570eeed25`
is the basis for the AST literal-label and bounded static source-location
projection. Tests compare those functions' ASTs, with only the delivery's own
static source label adapted.

Failure status contains an allowlisted outer phase, the verified preparation
module's allowlisted inner phase, a bounded exception class, an allowlisted
single-string literal label, and up to eight static public source/line rows from
at most 64 traceback frames. Zero- and multi-argument errors cannot become
labels. Unknown class names, error text, private paths, source text, frame locals,
and private buffers are not emitted. Only the already-public fixed staging
paths and pinned file inventory may be retained in creation reporting.

A protected projection fallback emits `DIAGNOSTIC_PROJECTION_FAILED` with
`cleanup_unknown=true`; already-reported fixed staging paths survive it. Cleanup
uncertainty from both delivery and preparation remains visible. The existing
five-second, 131072-byte direct JSON status boundary and no-retry behavior are
unchanged. Post-proposal verification has its own explicit outer phase.

## Reproduction

All fixtures are test-only exact public files under `fixtures/`: the three repaired
preparation sources, the frozen diagnostic, and the frozen recovery-kit manifest.
These fixtures are not staged, downloaded, or consumed by the delivery helper.
The diagnostic fixture is parsed for comparison, not executed. The manifest
fixture is read as JSON. Tests authenticate the fixture bytes. No private fixture
or mutable sibling directory is required.

Run each command with Python 3.6.8 or Python 3.12.14:

```
$PYTHON -I -B -S test_epoch7_prepare_delivery.py
$PYTHON -I -B -S test_epoch7_prepare_delivery_projection.py
$PYTHON -I -B -S test_epoch7_prepare_bootstrap_binding.py
```

Results are 41 retained boundary tests, 19 projection tests, and six bootstrap
checks on each interpreter, with zero errors, failures, or skips. Bootstrap tests
use a clearly synthetic commit only inside memory and mock the download; they do
not create a bound owner command. Network responses and orchestration calls are
mocked; filesystem operations use temporary local directories. No Git, network,
actual-host operation, private-plan preparation, or production action ran here.

Independent scoped review of the unbound source passed. The subsequent review
of the exact two-assignment publication binding and binding-test delta also
passed, independently reproducing all 66 tests on each interpreter. The actual
delivery publication and the owner template's own three-pin binding remain
pending. Production is HOLD and installation admission is NOT_GRANTED.
