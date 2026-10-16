# Local successor delivery candidate

Status: UNBOUND / NOT_AUTHORIZED. No public publication or host execution is authorized.

Production paths are fixed sibling roots under the existing candidate parent:
- epoch7-recovery-candidate-r7-claim-successor
- epoch7-preparation-candidate-r7-claim-successor (one preparation source only)

The adapter reuses the reviewed resource-bind downloader, safe archive extractor,
protected staging readers, bounded status projection and no-overwrite behavior.
All new artifact/source/preparer dependency pins remain None. An embedded extractor
checksum verifies the adapter's own shipped source, not publication authority.

After real publication and separate authorization, the intended finite path is:
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

The command description is deliberately non-executable. Focused local tests use
synthetic sources or immutable local fixtures and mocks for external/host boundaries.
