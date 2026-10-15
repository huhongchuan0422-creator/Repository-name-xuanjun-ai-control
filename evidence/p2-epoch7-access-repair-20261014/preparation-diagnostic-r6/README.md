# Read-only r6 preparation diagnosis

This separate endpoint explains the frozen preparation proposal's HOLD without changing its source or installing anything. Its only preparation operation is `propose-topology`, against the existing observation `1311b9e9fa97cfd4` and exact SHA-256 `b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246`.

It authenticates the immutable delivery source at `f21fc4f4efe1a2793740ebe45aa1e9f2ad88ba61`, then the same three preparation sources at `e8b9ebb3fb215fa5b1ef0a8dc0b31a77efd0ab67`. Both staging checks use `allow_create=False`: a missing, partial, changed or extra inventory causes HOLD, never repair. There are no staging writes, permission changes, removals, live probe runs, approval fetches or private-plan operations. The frozen preparer performs its existing source, protected-input, receipt and complete-topology validations.

Failure output adds the exact allowlisted inner preparation phase, a public-source literal label when available, and at most eight public-source-relative line locations. It excludes exception text, traceback content, private buffers and locals. Unknown exceptions have a static class fallback; projection failure has its own static HOLD. Cleanup uncertainty is retained. Delivery authentication, source verification, preparation and status output have separate finite budgets of 30, 60, 120 and 5 seconds. If status delivery itself fails, the process exits without an unbounded fallback or retry; the terminal report may then be unavailable.

A successful proposal contains an unsigned review body and host-validated evidence bindings. It is not by itself an independently reproduced raw-evidence audit packet or approval. A prior complete eight-case probe does not establish every nested readpath, SDK or server-denial assertion; stronger topology checks may still cause HOLD.

The observed outer HOLD did not preserve its first inner error. Independent source review found one deterministic downstream contradiction: the frozen native-binding reader expects `root:1002/0640`, while the successful r6 snapshot contract requires `root:root/0644`. The original unchanged reader is exercised in this test suite. This explains a guaranteed refusal if that reader is reached, not the unknown first error. The diagnostic does not repair or relax that contract.

## Local test evidence

Python 3.6.8 and 3.12.14 each pass 29 diagnostic tests and 4 bootstrap tests, with zero failures, errors or skips. Tests use authenticated public source fixtures, synthetic metadata and temporary files. They cover unchanged-reader refusal, real read-only staging, missing/partial/mismatched inventories, all error-reporting boundaries, bounded blocked output, no retry, exact observation/source bindings, and bootstrap pin-only substitution. They do not execute the host endpoint or reconstruct protected raw observation/receipt buffers locally.

Run each interpreter with `-I -B -S test_diagnose_preparation.py` and `-I -B -S test_bootstrap_template.py`. The diagnostic suite's documented sibling public fixtures are `r6-delivery-bound-candidate/epoch7_prepare_delivery.py`, the three production files in `r6-preparation-candidate/`, and `r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6/recovery-kit-manifest.json`. These are not private fixtures. Their immutable publications and hashes are recorded in the publication map.

## Publication and Owner bootstrap

Publish only the seven files named by `PUBLICATION_MAP.json`, plus that map, under its declared prefix and `P2_RETAINED_RECOVERY` feature mapping. No local logs, private observation, receipt or plan bytes belong in the publication.

`OWNER_DIAGNOSTIC_UNBOUND.txt` refuses before effects while its three publication pins are unset. After the diagnostic's real immutable publication is verified, substitute only `DELIVERY_COMMIT`, `DELIVERY_SHA256`, and `DELIVERY_BYTES` in a separate bound copy. Run `verify_bootstrap_binding.py --commit REAL_COMMIT --bound-file BOUND_COPY` on both interpreters and obtain an independent pin-only review before manual Owner delivery. The bootstrap uses the previously observed existing `/usr/libexec/platform-python3.6` interpreter. Do not execute either bootstrap locally as a test.

Production remains HOLD. Host diagnosis and any later repair require separate evidence.
