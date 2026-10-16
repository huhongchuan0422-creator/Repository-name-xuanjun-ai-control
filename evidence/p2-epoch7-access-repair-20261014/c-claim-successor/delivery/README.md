# Source-bound successor delivery candidate

Status: BOUND_REQUIRES_SEPARATE_AUTHORIZATION. Publication does not authorize host execution.
The original reviewed UNBOUND source checkpoint is preserved separately.

Exact source commit: f4345dd385de9b87dc821cd26bb42bb9b045d03f.
Exact source tree: 235a78f5aafc3e60a50ac29f52a9cf86d5cbb965.
Verified artifact and preparation dependency publication:
bdc8d6da448a5678588da9878536828f07e1a14e.
All artifact/source/preparer pins and both immutable dependency URLs are now bound.
The embedded extractor checksum authenticates the embedded extractor bytes;
adapter identity is verified separately.

Production paths remain fixed sibling roots under the existing candidate parent:
- epoch7-recovery-candidate-r7-claim-successor
- epoch7-preparation-candidate-r7-claim-successor (one preparation source only)

The finite preparation path requires separate authorization:
1. Validate every pin before any network or host read/write.
2. Download exact pinned preparation source and archive; inspect the whole archive
   and authenticate every member, manifest, entry and source identity before mkdir.
3. Exclusively stage the new kit; an existing root must fully verify. Never repair.
4. Exclusively stage the one-file preparation sibling, or fully verify existing bytes.
5. Call prepare(expiry, deadline) exactly once with its separate 120-second budget.
6. Reverify both staging inventories and report the three private output descriptors.

A failure preserves partial/staged roots and all created outputs. There is no cleanup,
retry, resume, probe, claim/journal mutation or service action. The fresh predecessor
read and original input authentication are owned by the preparation tool. Preparation
creates a proposal, never installation admission or final approval.

The command description remains deliberately non-executable and supplies no expiry.
The focused 47-case suite uses synthetic archive/entry fixtures, explicitly mocked
host/external boundaries and local disposable filesystem staging. Bound dependency
source is checked without invoking preparation. Explicit false/None refusal tests
remain active. Local tests can select a separate preparation directory through
EPOCH7_SUCCESSOR_PREPARATION; the default assembled path remains preparation/.
