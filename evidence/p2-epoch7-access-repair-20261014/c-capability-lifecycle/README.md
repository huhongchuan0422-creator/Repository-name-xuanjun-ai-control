# Capability lifecycle correction

Local candidate for original Task5 design decision [PR58 comment 6218328313](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/58#issuecomment-6218328313).

## Finding and scope

The prior Owner terminal reported CLAIM_SUCCESSOR_CAPABILITY_EXPIRED after all commit checks returned, before either new claim was attempted. Its predicate included both monotonic and UTC conditions; no per-step clocks were retained, so the historical clock branch is not independently established.

The revised, explicitly versioned contract consumes the prepared start handle within 30 seconds, performs all original guarded checks, then privately mints publication within the minimum of mint+30, the already-running final-inner guard and the immutable prepare UTC-to-monotonic ceiling. This does not increase original individual guard budgets. See C_TRANSACTION_SEMANTICS.md.

The immutable resourcebind archive supplies the same historical baseline; fifteen exact overlays preserve all 107 runtime payloads, all 110 runtime package files and all 16 business phases. The previous published claim-successor candidate remains separate. The new fixed root is epoch7-recovery-candidate-r7-claim-lifecycle; fresh private preparation uses a separate sibling and output names.

## Current evidence status

The source includes 40 focused lifecycle cases plus the preserved 55 transaction/protected-write cases and supporting collector/preflight/routing/factory/census regressions. The source-stage explicit CI harness expects 324 focused cases: 26 collector + 11 preflight + 27 routing + 26 factory + 12 census + 55 transactions + 40 lifecycle + 30 preparation + 47 delivery + 50 builder; it adds 46 CI contracts and two outer checks. Counts are enforced against actual unittest results with zero skips.

Individual Python 3.12.14 lifecycle40, transactions55, preflight11, factory26, routing27, preparation30, delivery47 and builder50 runs passed locally. The complete exact-checkout rehearsal and final Hosted records remain separately recorded results, not inferred from expected counts. Native local Python3.6.8 produced completed delivery47/preflight11 passes and earlier lifecycle36 passes, but final lifecycle38/core55/routing27 runs had pre-test native crashes, while factory/preparation fixture subprocesses also failed. These observations are retained as compatibility limits, not full native passes. No repeated crash diagnosis or preload workaround is used. The exact source-stage official Hosted run recorded below provides clean Python3.6.15 compatibility for those source bytes; the earlier local failures remain separate historical results.

The actual compiler identity below now exists. No new private Plan or host execution authority exists for this lifecycle version. Synthetic fixture zero identities must never be reported as real publication IDs. Historical test aliases inside the immutable archive are retained as authenticated fixtures; the new explicit harness is the authoritative test inventory and does not claim every historical entry test alias passes.

## Exact previous approval formatting provenance

The byte-level audit resolved the old PR58 comment 6217316166 byte discrepancy: the earlier 8948-byte/SHA256 944558c0d0debc9d95fd9da6175fd7f1a16dee74b3bd93509e861c594ec67af7 body comprised the final 7880-byte/SHA256 4dfa1b95b304c2bc403872c815e976f15b7726f59cbfb8de668920c93019d5e0 marker+JSON, two LF bytes and 1066 bytes of explanation. The candidate JSON remained exactly 7826 bytes/SHA256 005d487dacdda1954fcfa0462fa01be133ce8452e1e5bdf9065c1bd99f87587e. The explanation is preserved as comment 6217360181; the actual prior C command used the corrected 4dfa1b95 whole-comment binding. This history neither extends its expiry nor authorizes the new timing contract.

## Privacy and execution limits

No private Seed, retained observation, terminal transcript or private configuration is part of the public source package. Preparation and execution have distinct approvals and effects. The only new public diagnostic material is finite timing metadata; a future startup wrapper must explicitly project it. Failure or missing evidence stays HOLD/UNKNOWN, without automatic retry.

## Actual immutable publication and selected artifact

Compiler source commit: 105996ed06a0bdb5d025914cf08ebd448425f739.
Compiler source tree: 343d315b3ead6266a626b5875dbdd6c2fa0309af.
Dependency commit: e2df38160e635af96dcfd63a1b75cf64671e4935.
Dependency tree: ac85f40c5717ccf147606d265808e629127cc918.
The final delivery checkout is a later identity, never substituted for the compiler source.

Selected Python3.12 archive: 1074448 bytes, SHA256 bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3.
Manifest: 62752 bytes, SHA256 91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392.
Entry: 56593 bytes, SHA256 21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890.
All 257 files/256 cache pins and 42 directories were checked; the 107 payloads and
110 runtime package files remain byte-identical. The source-bound build-result
records the complete input/output inventory.

Bound preparer: 37390 bytes/SHA256 71b7f9b6a63e96042194b218042a44929ed51033065c445aa9281feae76b38f5.
Bound delivery: 42469 bytes/SHA256 252385a552b81f6c3c390bdace95a013dc07db0afffef276739bac67b463106a.
Binding modifies five preparer and eleven delivery top-level literals only. The
public invocation description remains non-executable and has no chosen expiry.

## Actual validation, including intermediate limitations

Source Hosted run38924556983 on exact105996ed06a0bdb5d025914cf08ebd448425f739
completed successfully. Official Python3.6.15/job117052668694 and
Python3.12.15/job117052668882 each passed 372 = 324 focused +46 contracts +2 outer
checks, with zero errors, failures or skips. Python3.12 gzip matches the selected
archive. Python3.6 gzip is1074517/SHA256
25351c655a07afcc47b53e49048259b949eb9d1a67a7540b3ff0aeb2a18f03da; its compressed
bytes differ while the manifest and all257 uncompressed files match.

Before publication, one local exact-checkout run failed a composed preparation
fixture PATH_IDENTITY check. The observed ancestor difference was not retained,
so the cause is not assigned to shared/tmp contention. The test was corrected
only by mapping its absolute filesystem namespace to a private anchor; actual
open_chain/recheck/DescriptorTree/publication and per-ancestor drift/symlink
rejection remain exercised, with a separate unwrapped traversal test. Production
source was unchanged. The final exact-checkout source rehearsal passed372.

Intermediate dependency checkout e2df38160e635af96dcfd63a1b75cf64671e4935
run38925474291 failed: Python3.6.15/job117055781378 and
Python3.12.15/job117055780914 each passed46 contracts, but the old source-stage
fixture adapter rejected PUBLIC_FILE_PIN before starting the focused suite. Its
workflow outer check passed. The dependency commit had updated three preparer
files while that intermediate adapter still pinned the prior source-stage bytes;
the raw log does not identify the first rejected path. This failure is retained,
not treated as a final-bound result. The final CI explicitly updates those pins
and separates fixed compiler/dependency identities from its current checkout.

The final-bound harness adds one exact preparer binding case:325 focused,55 CI
contracts and2 outer checks, expected total382. Its final exact-checkout and Hosted
results are separate records; final Hosted is PENDING at this document freeze.
No current or historical source/CI result constitutes staging, preparation or
installation permission. A new exact private Plan/Seed/Packet and full approval
are required; the old 16:00UTC approval is neither reused nor extended.
