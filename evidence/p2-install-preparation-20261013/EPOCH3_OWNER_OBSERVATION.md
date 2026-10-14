# Epoch 3: Owner read-only observation, 2026-10-14

Source: Owner attachment message Sentinel_c0815665c7ac8191b71a0961cd080af2.
Collector commit: aa84c354350b57b9e9cd9a9de000115a0078d376.
Collector SHA256: 1b6197cdcb83d290e5e4995cd5b3b76a76db4ad51299ea285a08d21180c12c48.
Original attachment SHA256: 4249d32ed5ae94169064dafe7bf21072991cb60c0e8f3e5f892f0f29c59f86f6.
Canonical observation SHA256 (without newline): 49b8a78da82c38e5d17f54a32538e0595477894e249cb4a125d4d606750b0883.
The attachment and observation hashes were recomputed locally and matched.
Private credential material is not reproduced in this public summary.

## Observed, not general production acceptance

- Epoch remains 3; 8 pinned receipt/plan files matched before and after observation.
- 24 provision targets match recorded pre-effect states (absent or original masks).
- 7 bootstrap files match journal publication identity/hash/ownership/mode;
  temporary names are absent. They must not be recreated or silently overwritten.
- 16 installed RPM versions match the recorded candidates. Version checks do NOT
  assert full RPM installed-file integrity and are not permission to rerun DNF.
- 2 publisher roots match journal inode/device and their stage names are absent.
  Full recursive publisher content was NOT checked by this collector.
- UK Python3.6.8 / Certbot1.22.0 parses the identical issuance argument sequence
  using a private regular empty configuration file: returncode 0, no stderr.
  Only prepare_and_parse_args ran; no certificate request, main, or renewal ran.
- TLS config/work/log directories are empty. Production mutations: 0.

## Follow-on source work

verify_retained_publisher.py supplies a bounded descriptor-anchored recursive
comparison using the SAME original journal fingerprint format. It rejects scan
errors, aliases, special files, hardlinks, metadata drift, listing races, mounts,
wrong ownership/modes and content mismatch; it emits no file contents. A dedicated
root-host entry checks the exact publisher journal before and after observation.
16 local Python3.6.8 tests PASS, including original-format compatibility. These
are scratch tests only; actual UK publisher content comparison remains PENDING.

## Remaining complete recovery packet

Updated runtime, new immutable manifest and rendered identities, finite epoch3
release rebinding, preserved old journals, reuse of verified completed resource
publication, full failure/retain path, UK integration tests and one consolidated
independent exact-version review are still required. No install/resume command
is authorized by this observation; previous one-shot approval was consumed.

PRODUCTION_RECOVERY=HOLD
INSTALL_ADMISSION=NOT_GRANTED
