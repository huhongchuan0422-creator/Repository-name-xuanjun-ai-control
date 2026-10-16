# Local capability-lifecycle delivery candidate

Status: UNBOUND / NOT_AUTHORIZED. No public publication or host execution is authorized.

Production paths are fixed sibling roots under the existing candidate parent:
- epoch7-recovery-candidate-r7-claim-lifecycle
- epoch7-preparation-candidate-r7-claim-lifecycle (one preparation source only)

The adapter reuses the reviewed resource-bind downloader, safe archive extractor,
protected staging readers, bounded status projection and no-overwrite behavior.
All new artifact/source/preparer dependency pins remain None. An embedded extractor
checksum verifies the adapter's own shipped source, not publication authority. The
extractor delta is only its fixed lifecycle root; the exact changed source is embedded.
The old resourcebind and claim-successor siblings are never modified or adopted.

After real publication and separate authorization, the intended finite path is:
1. Validate every pin before any network or host read/write.
2. Download exact pinned preparation source and archive; inspect the whole archive
   and authenticate every member, manifest, entry and source identity before mkdir.
3. Exclusively stage the new kit; an existing root must fully verify. Never repair.
4. Exclusively stage the one-file preparation sibling, or fully verify existing bytes.
5. Call prepare(expiry, deadline) exactly once with its separate 120-second budget.
6. Reverify both staging inventories and report the three private output descriptors,
   using distinct epoch7-lifecycle-approved-plan-, epoch7-lifecycle-resume-inputs-,
   and epoch7-lifecycle-review-packet- prefixes.

A failure preserves partial/staged roots and all created outputs. There is no cleanup,
retry, resume, probe, claim/journal mutation or service action. The fresh predecessor
read and original input authentication are owned by the preparation tool. Preparation
creates a proposal, never installation admission or final approval.

The command description is deliberately non-executable. Focused local tests use
synthetic sources or immutable local fixtures and mocks for external/host boundaries.

The 47-case delivery suite passes on Python 3.12.14 with `-I -B -S` (local log:
`test-lifecycle-python312.log`). It tests source binding, synthetic archive layout, exact
roots and prefixes, retained partial output behavior, and safe status projection.
Its generated entry/archive are explicitly synthetic and prepare is mocked. It
does not authenticate a real published lifecycle archive or exercise host admission.
New policy compilation is covered by the separate real-core preparation suite.

One isolated Python 3.6.8 invocation also passed all 47 delivery cases in 0.577s
(`test-lifecycle-python368.log`). This uses the same explicit synthetic entry and
archive and mocked prepare boundary; it does not resolve the preparation suite's
separately recorded native fixture failure. No retry was performed.
