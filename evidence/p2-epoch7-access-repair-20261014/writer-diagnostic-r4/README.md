# Fixed r4 writer-pair diagnostic

FEATURE_ID: P2_RETAINED_RECOVERY

This standalone diagnostic uses the already installed, immutable r4 kit. It does not change the kit, its manifest, the runtime, the admission predicates, or the full writer-equality comparison.

## Exact operation

1. Require root:root, the fixed UK hostname, and Python `-I -B -S`.
2. Read the entry through protected no-follow descriptors and verify its exact SHA before compilation. Authenticate the entire existing r4 kit against manifest `0f233ca650ddacc6b0ad969813bc192f1a9031286666dd28dedb265e8d34211c`.
3. Authenticate the fixed prior observation `cbb34efd83eadd357f6f24939769257d845c027de8028cca036e35fdcce53a53` and its linked continuation receipt `464da1458ba040d996cb5003199e825a14465e4c1a7f6738a36582b9f2f9131f`. Require the stored primary failure to be `WRITER_OBSERVATION_CHANGED`.
4. Within one authenticated import context, acquire the two existing install/activation locks with the frozen nonblocking API. Call the unchanged `observe_with_io` once. Its real measured-policy builder and collector run unchanged.
5. A narrow `ObservationIO.writers` subclass calls the unchanged base, bounds serialization, validates the returned row with the frozen validator, and retains a deep copy. It returns the original object unchanged. The attempted-call bound is checked before invoking the base; at most two calls are allowed.
6. Retain the original outcome, release owned locks, and reverify entry, whole kit and both prior files. Print only a bounded JSON report of fixed section/subfield names, counts and digests. No raw process identities, paths from control-file maps, argv, configuration, environment, SQL contents, policy, snapshot or evidence bodies are printed.

A changed writer pair still raises the original HOLD. Even a fully equal pair does not grant admission. Later retained reread/database checks remain explicitly unreached after the original writer mismatch. Aggregate process changes are not attributed to benign churn. Probe/unit/source/OpenClaw ancillary reports are deliberately not recollected; they are unnecessary for the independently complete core measured-policy path.

## Effects and bounds

No chmod, permission repair, disposable UID fixture, service action, probe, production resume, recovery claim, persistent diagnostic output, or production-data write is called. The reused observation APIs perform local systemctl/RPM/git/openssl queries and disposable SQLite-copy analysis. RPM may update its own locks/shared bookkeeping, and temporary SQLite copies may be created and removed. This is not a claim of literally zero filesystem writes.

The separate recurring-alarm budgets are 600 seconds for initial authentication and collection, 60 seconds for final authentication, and 10 seconds for projection. The optional publication bootstrap adds a separate 30-second HTTPS download budget; it rejects proxies, redirects, altered lengths and hashes before compilation, clears its timer, then calls the verified diagnostic with no arguments. The budgets do not bound sudo/interpreter startup or uninterruptible kernel calls. KeyboardInterrupt/SystemExit and known cleanup uncertainty are reported without replacing the primary outcome. Abrupt process death cannot guarantee a final report.

Each retained writer sample is bounded to 4 MiB. The public report is bounded to 64 KiB. No automatic retry is implemented. A partial result or cleanup uncertainty remains nonzero HOLD. A successful diagnostic is still not production acceptance.

## Validation

48 synthetic/fixture tests pass on Python 3.6.8 and 3.12.14. Six cases load the actual published 249-member archive and 248-file authenticated cache, exercising the unchanged collector and the real measured-policy/observe-with-IO path using explicitly synthetic host data. They cover unchanged success, original writer mismatch, invalid-row refusal and later retained-file race. No actual host operation is executed by these tests. The fixture archive and extractor are hash-verified before execution.

The bootstrap has 23 mocked/compile-only tests passing on both interpreters. Its immutable publication commit remains unset until the parent publishes and reads back exact bytes. No unbound bootstrap is deliverable.

One intermediate test-only failure is retained locally: hashing Python 3.12 AST rendering was not portable to Python 3.6. The comparison now hashes exact unchanged function source slices. No production behavior or expected safety predicate was changed to obtain the pass.

Real UK execution of this diagnostic remains NOT_RUN at this receipt. Publication and Owner delivery are parent-controlled gates. Existing full-kit CI evidence is unchanged and is not presented as execution of this new standalone diagnostic.
