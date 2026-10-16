# Capability lifecycle correction

Local candidate for original Task5 design decision [PR58 comment 6218328313](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/58#issuecomment-6218328313).

## Finding and scope

The prior Owner terminal reported CLAIM_SUCCESSOR_CAPABILITY_EXPIRED after all commit checks returned, before either new claim was attempted. Its predicate included both monotonic and UTC conditions; no per-step clocks were retained, so the historical clock branch is not independently established.

The revised, explicitly versioned contract consumes the prepared start handle within 30 seconds, performs all original guarded checks, then privately mints publication within the minimum of mint+30, the already-running final-inner guard and the immutable prepare UTC-to-monotonic ceiling. This does not increase original individual guard budgets. See C_TRANSACTION_SEMANTICS.md.

The immutable resourcebind archive supplies the same historical baseline; fifteen exact overlays preserve all 107 runtime payloads, all 110 runtime package files and all 16 business phases. The previous published claim-successor candidate remains separate. The new fixed root is epoch7-recovery-candidate-r7-claim-lifecycle; fresh private preparation uses a separate sibling and output names.

## Current evidence status

The source includes 40 focused lifecycle cases plus the preserved 55 transaction/protected-write cases and supporting collector/preflight/routing/factory/census regressions. The explicit CI harness expects 324 focused cases: 26 collector + 11 preflight + 27 routing + 26 factory + 12 census + 55 transactions + 40 lifecycle + 30 preparation + 47 delivery + 50 builder; it adds 46 CI contracts and two outer checks. Counts are enforced against actual unittest results with zero skips.

Individual Python 3.12.14 lifecycle40, transactions55, preflight11, factory26, routing27, preparation30, delivery47 and builder50 runs passed locally. The complete exact-checkout rehearsal and final Hosted records remain separately recorded results, not inferred from expected counts. Native local Python3.6.8 produced completed delivery47/preflight11 passes and earlier lifecycle36 passes, but final lifecycle38/core55/routing27 runs had pre-test native crashes, while factory/preparation fixture subprocesses also failed. These observations are retained as compatibility limits, not full native passes. No repeated crash diagnosis or preload workaround is used. Final clean official Hosted3.6.15 compatibility remains required.

No published compiler identity, new private Plan or host execution authority exists for these bytes. Synthetic fixture zero identities must never be reported as real publication IDs. Historical test aliases inside the immutable archive are retained as authenticated fixtures; the new explicit harness is the authoritative test inventory and does not claim every historical entry test alias passes.

## Exact previous approval formatting provenance

The byte-level audit resolved the old PR58 comment 6217316166 byte discrepancy: the earlier 8948-byte/SHA256 944558c0d0debc9d95fd9da6175fd7f1a16dee74b3bd93509e861c594ec67af7 body comprised the final 7880-byte/SHA256 4dfa1b95b304c2bc403872c815e976f15b7726f59cbfb8de668920c93019d5e0 marker+JSON, two LF bytes and 1066 bytes of explanation. The candidate JSON remained exactly 7826 bytes/SHA256 005d487dacdda1954fcfa0462fa01be133ce8452e1e5bdf9065c1bd99f87587e. The explanation is preserved as comment 6217360181; the actual prior C command used the corrected 4dfa1b95 whole-comment binding. This history neither extends its expiry nor authorizes the new timing contract.

## Privacy and execution limits

No private Seed, retained observation, terminal transcript or private configuration is part of the public source package. Preparation and execution have distinct approvals and effects. The only new public diagnostic material is finite timing metadata; a future startup wrapper must explicitly project it. Failure or missing evidence stays HOLD/UNKNOWN, without automatic retry.
