# Fixed r5 writer-pair attribution diagnostic

FEATURE_ID: P2_RETAINED_RECOVERY

This standalone diagnostic authenticates the installed r5 kit and fixed previous HOLD/receipt. It calls the original measured-policy builder and collector once under the two existing install/activation locks. The r5 semantic comparison is unchanged: every writer-safety field is compared exactly, while the aggregate FD count is retained as telemetry. No installed source, runtime, manifest or admission rule is modified.

## What is observed

At most two original writers calls are allowed. Validated bounded copies are retained while the exact original objects are returned unchanged. The report contains fixed section/field names, counts and digests. Canonical typed equality is used for diagnostic differences, including boolean/integer distinctions.

For the original process scan only, a temporary profile hook observes the authenticated scan and nested procfile code objects. It requires exact self and scan-frame identity and accepts only direct-return stat and comm data. It temporarily retains at most32MiB of original stat/comm bytes, the original numeric PID map and scalar FD counts. It does not read /proc again or retain status, argv, environment, executable paths, cgroups or descriptor target names.

After the original scan returns, the PID map must match its returned digest and FD count. Exactly two direct stat returns and one comm return are required for every PID. Both PID/starttimes and kernel flags must agree; per-PID counts must sum to the original FD total. The hook is removed on every path. Existing trace/profile hooks are refused, and cleanup uncertainty is fatal HOLD. Raw temporary references are cleared after validation.

The output identifies added/removed/changed numeric PID/starttime/UID rows. When the exact same-call detail checks pass, it also reports the kernel-thread flag, comm SHA, a finite observed-name label, and FD count. An observed name does not prove executable identity, a trusted daemon role or benign churn. Executable/cgroup/FD-target attribution remains unavailable. Missing, raced, malformed or over-bound capture is explicitly UNKNOWN. At most64 changed rows are printed with full counts, changed-PID-set digest and truncation status. Overall pair coverage and process-attribution coverage are separate. Diagnostic timing can itself perturb the measured system; this does not justify treating any resulting drift as benign.

## Effects and bounds

The existing protected r5 kit, prior observation53c578a2eaa872d24dc06cf1bbaacd1f0dbc4746b36f73802d01bc8f334d16a0, and linked receipt a12d0b5107e78748239a1002667db14a354fd07e031e248c9486ff9d7dceb99c are hash checked before collection and again afterward. The entry is SHA-checked before compilation. No chmod, UID fixture, probe, service mutation, production resume, recovery claim or persistent diagnostic output is called. Reused observation APIs perform systemctl/RPM/git/openssl queries and disposable SQLite-copy analysis. RPM bookkeeping and temporary SQLite copies are possible; this is not a literal zero-filesystem-write claim.

Recurring-alarm budgets are separate:600 seconds for authentication/collection,60 seconds for final authentication,10 seconds for projection. The optional HTTPS bootstrap has a separate30-second download budget and verifies exact immutable URL, length and SHA before compilation. Sudo/interpreter startup and uninterruptible kernel calls are outside these Python budgets. Interruptions and cleanup uncertainty preserve primary failure evidence. Abrupt process death may prevent a final report. No automatic retry is implemented.

Writer samples are bounded to4MiB each, the numeric census to2MiB, transient stat/comm data to32MiB, and public JSON to64KiB. Original collector HOLD and later-check coverage remain visible; an equal pair or completed diagnostic never grants production admission. Ancillary probe/unit/source/OpenClaw reports are not recollected.

## Local verification and release gates

85 tests pass on Python3.6.8 and3.12.14, with zero skips. Ten tests use the actual250-file archive/249-file cache. These exercise the original r5 collector and measured-policy path, count-only drift acceptance, real safety-digest and typed-value rejection, later retained-file race, and the actual frozen process scan with precisely its original mocked /proc reads. Other cases cover strict same-code/self filtering, indirect SSH exclusion, start/kernel drift, secret-safe comm labels, profile cleanup/interruption, bounds and worst-case full19-unit output.

The separate bootstrap has23 mocked/compile-only tests on both interpreters. Real host execution and live process attribution remain NOT_RUN. Publication, immutable byte readback and Owner delivery are parent-controlled gates. Existing full-kit CI is unchanged and is not evidence of executing this new standalone diagnostic.
