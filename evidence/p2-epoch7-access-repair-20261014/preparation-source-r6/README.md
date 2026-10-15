# Artifact-bound r6 preparation candidate

This separate candidate preserves the frozen r5 preparation files and historical
public fixture. It binds the immutable r6 kit produced from source
0c8a0f2a97da0c3f00f53659cd6ef7fc7d4ec3ba, tree
7d0f402b495b1398637c86463d9c10b4d4559d1f, and published at artifact commit
1b7d382acc9e78d907b42f20d39b74b913e098f4. Its exact manifest and entry hashes
are embedded in the wrapper. The kit and preparation directories are new r6
siblings; no r5 directory is overwritten.

The topology adapter pins the reviewed corrected probe helper, driver and Node
receipt validator from that artifact. A complete result requires incomplete_case
to be absent (legacy compatibility) or exactly None. Dicts, lists, booleans,
numbers and strings are rejected even when all eight cases and aggregate
success are present. The protected receipt has the same requirement through
the pinned Node validator.

Clean OUTPUT_CAPTURED records retain the exact historical four-key schema.
The driver's error-only non_json_diagnostic field is rejected by that strict
schema, including an unexpected explicit None. No diagnostic text is copied to
topology output and no failure metadata can authorize a complete topology.

The preparation/data implementation and all original public tests are preserved
except for r6 artifact and fixture locations, exact corrected source pins, the
incomplete-case guard and additive regressions. Data bytes are unchanged. No
review IDs or private plan are generated. Genuine topology review and existing
final plan approval remain separate mandatory gates; production remains HOLD.

Run the complete public-fixture suite with either isolated interpreter:

    python3 -I -B -S run_local_tests.py --portable --kit-root "$VERIFIED_R6_ROOT"

The exact portable suite has 87 tests and requires zero errors, failures or
skips. It authenticates the complete real r6 fixture and its cached import
closure; compilation cases use synthetic inputs only. The public map contains
exactly seven public files and all 250 fixture files. Private plans, observations
and the private reproduction suite are excluded. Actual private-plan preparation,
UK observation/probe, topology review, production approval and installation have
not been performed by these tests. Earlier unbound-only logs and the unbound
harness are local historical material, excluded from the public map.
