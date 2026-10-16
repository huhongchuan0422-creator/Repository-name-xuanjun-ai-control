# Local capability-lifecycle delivery candidate

Status: exact immutable dependencies BOUND / HOST EXECUTION NOT_AUTHORIZED.

Production paths are fixed sibling roots under the existing candidate parent:
- epoch7-recovery-candidate-r7-claim-lifecycle
- epoch7-preparation-candidate-r7-claim-lifecycle (one preparation source only)

The adapter reuses the reviewed resource-bind downloader, safe archive extractor,
protected staging readers, bounded status projection and no-overwrite behavior.
All artifact/source/preparer dependency pins are now bound to the exact identities below. The embedded extractor checksum authenticates the embedded extractor bytes;
adapter identity is verified separately. The
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
Its generated entry/archive are explicitly synthetic and prepare is mocked. The earlier synthetic suite did not authenticate the later published lifecycle archive or exercise host admission. The actual archive and final literal binding are separately verified below.
New policy compilation is covered by the separate real-core preparation suite.

One isolated Python 3.6.8 invocation also passed all 47 delivery cases in 0.577s
(`test-lifecycle-python368.log`). This uses the same explicit synthetic entry and
archive and mocked prepare boundary; it does not resolve the preparation suite's
separately recorded native fixture failure. No retry was performed.

## Exact dependency binding

Dependency source/archive commit: e2df38160e635af96dcfd63a1b75cf64671e4935.
Compiler source:105996ed06a0bdb5d025914cf08ebd448425f739/tree343d315b3ead6266a626b5875dbdd6c2fa0309af.
Archive:1074448/bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3. Manifest:91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392.
Preparer:37390/71b7f9b6a63e96042194b218042a44929ed51033065c445aa9281feae76b38f5. Delivery:42469/252385a552b81f6c3c390bdace95a013dc07db0afffef276739bac67b463106a.
Only eleven top-level assignment values differ from the reviewed unbound source;
all functions/classes and the embedded extractor remain byte-identical. Four
affected binding tests retain explicit missing/None/UNBOUND rejection. The final
CI independently reconstructs the compiler from its fixed source identity and
compares all257 selected contents, without requiring cross-version gzip equality.
No private expiry, approval ID or host command is chosen by this public package.
