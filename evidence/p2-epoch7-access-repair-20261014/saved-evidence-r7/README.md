# Fixed R7 saved evidence export

This candidate supports one saved-data-only export for observation
`8df3b22b3762070f`, nonce `cee45858d9d19863e977e2648bc2196a`.
It does not collect a new observation, run a probe, prepare or install a plan,
change permissions, obtain an approval, or resume production.

## Inputs and authority

The root-only isolated command authenticates the existing immutable R7 entry,
manifest and every cached source. It reads only the fixed observation and normal
diagnostic receipt, then the exact nonce's created receipt named and hash-bound
by that authenticated observation. Reads use the previously reviewed held,
no-follow descriptors, authority/ACL checks, size limits and before/after checks.
The same fixed reads and kit authentication repeat before output. No source is
staged on the host. Three pure sources are embedded with exact size/hash and
bounded compressed decoding; their source manifest has no self-reference.

Known external anchors are the raw observation SHA256 `a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68`,
normal receipt SHA256 `f3b0a8dbcf0dc1af943c92080504bcadd83c675524d9cbff93136eab0f503490`,
core-policy SHA256 `9932270a1835dbf42df57dce5aa11933ef5795bb77b9a411b3a4f26c24f7b27a`,
snapshot SHA256 `9bc4a56f28264698058245f47bce8747d9ee96218076c7bbb25d4f1b7aefd4d8`,
and the exact R7 source/runtime/kit pins in the exporter. Newly derived receipt,
normalized-observation, topology, evidence and unsigned-body hashes are not
invented or copied from R6.

## Distinct saved inventory and limits

Schema2 binds all11 units and33 drop-in roots in the saved unit-metadata section,
the exact section/full-metadata digests, and the measured command-resolution
branch whose pinned collector performs the late full-inventory check. It never
manufactures directory or parent inode stamps. Existing service drop-ins may
expose only validated Type/User/Group/SupplementaryGroups public fields; socket
content remains unsupported. Unknown keys or unsafe strings fail closed.

The new topology review body uses `saved_unit_dropins_sha256` and
`saved_projection_source_manifest_sha256`. It is incompatible with the old R6
schema1/EXACT_PRE_POST proof. A future final-plan adapter must separately collect
fresh authority metadata and require exact content/presence equality to the
reviewed saved inventory. Those fresh checks must not replace the reviewed
saved proof or silently change its body hash. That adapter and installation
admission remain pending; this export grants neither.

The full private observation remains on the host. Genuine R7 pure validators
validate its core and ancillary bindings before projection. Offline review
recomputes the exported subset only, not the hidden whole observation. The
first R7 attempt's HOLD is separate evidence and is not explained or admitted
by this later successful observation.

## Public export boundary

The single output packet is bounded to524288 bytes. It contains the finite
probe policy, eight case rows, server observations, Node proof, exact receipt
JSON and canonical+LF bytes, resource/event/cleanup metadata, saved11-unit/33-root
inventory and derived topology/unsigned review body. Metadata includes fixed
paths, numeric identities, timestamps, capabilities, namespace labels and
hashes. Raw configuration, environment values, arbitrary command strings,
stdout/stderr, private source buffers and the whole observation are excluded.
Every nested field is allowlisted; an unknown field or unsafe value yields HOLD
instead of a partially redacted reproducibility claim.

The collection/projection stage has a60-second recurring alarm and output a
separate60-second budget. The network bootstrap has its existing separate
30-second recurring overall download alarm and10-second socket timeout. Primary failure and cleanup uncertainty are retained.
No automatic retry is performed. The published bootstrap remains unbound until
an actual immutable publication is read back and approved for delivery.

## Offline verification

Use the exact received packet file and obtain its SHA256 independently from
that received file, not from a field inside the packet. With the authenticated
public R7 archive:

    python3 -I -B -S verify_exported_evidence.py PACKET_JSON R7_ARCHIVE EXTERNAL_PACKET_SHA256

The verifier checks the pinned exporter, embedded pure sources, archive,
manifest and all252 cached files. It checks known observation/receipt anchors,
strict schema and all cross-bindings, then reproduces seven subset hashes.
PASS_EXPORTED_SUBSET_ONLY is not an independent whole-observation proof,
approval, current-host state claim, or authority to install.

## Reproducible local tests

The disposable layout has sibling directories `saved-r7-evidence-export-candidate`
and `r7-saved-preparation-candidate`. Set EPOCH7_PREP_TEST_KIT_ROOT to the extracted,
authenticated R7 kit and EPOCH7_EXPORT_TEST_ARCHIVE to its exact archive. Run with
PYTHONDONTWRITEBYTECODE=1 and -I -B -S:

    python3 -I -B -S run_local_tests.py orchestration
    python3 -I -B -S run_local_tests.py schema
    python3 -I -B -S run_local_tests.py bootstrap
    python3 -I -B -S ../r7-saved-preparation-candidate/test_epoch7_topology_projection.py
    python3 -I -B -S ../r7-saved-preparation-candidate/test_epoch7_prepare_data_r7.py

Fixtures are public synthetic metadata. Actual archive/core imports and the
full factory data validator are exercised, while host methods are never run.
Historical failures remain local evidence and do not count as passing results.
