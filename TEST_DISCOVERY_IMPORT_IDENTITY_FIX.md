# Full-discovery import identity fixture fix

## Observed failure

`python3 -m unittest discover -s tests -v` previously ran 36 tests with one
error. `tests/test_p3_host_boundaries.py` and
`tests/test_p3_qa_counterexamples.py` inserted `src/` into global `sys.path`
and imported `p3_host_boundaries` as a top-level module. The later callsite
test imported the same source as `src.p3_host_boundaries`. Python therefore
created two distinct `TrustedReceiptProvider` class identities from the same
bytes, so the legitimate package-form provider failed `isinstance` with
`TRUSTED_RECEIPT_PROVIDER_REQUIRED` only under full discovery order.

## Minimal fix

Both historical tests now import `src.p3_host_boundaries`, matching the
callsite tests. The global `sys.path` mutation was removed. No runtime,
installer, admission, receipt-validation, default-off, recovery, rollback, or
host behavior changed. The strict provider type check remains unchanged.

## Verification

- affected targeted suite: 36/36 PASS;
- full discovery suite: 36/36 PASS;
- production/root/installation effects: 0.
