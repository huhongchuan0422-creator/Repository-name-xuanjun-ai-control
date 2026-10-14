# Complete offline inputs for the remaining independent render gate

Continue PR58 requests6166097735/6166262602, response6167132248, reviewer6167232965.
This evidence-only supplement does not alter frozen recovery source07e81116, its254327-byte kit, production entry, runtime102, or compiled plan. No new install authority.

## Inputs available through GitHub text reads

1. `original-102-runtime-archive.base64.txt` in this evidence commit. Base64 transport of the ORIGINAL192286-byte p2-candidate.tar.gz extracted without recompression from original artifact ZIP11865804223. ZIP SHA256099271480e82f28d8d4a0f1ceb9c2f2e4efc493af26dbaa9e106bfaf785f2dd5; archive SHA256c2d593d662fbce4a0c2fa454cc4a18dbec327c0bd0bf3d6d72849d9a5a79970d. These are independently pinned in historical PR58 review6159933373. All105 original regular members remain byte-identical;102runtime plusmanifest/provenance/freezer. This is NOT a reconstruction using current files.
2. `epoch3-recovery-kit.base64.txt` at evidence commit3e473efc282c2955191411497e4b86b7a1aba937. New frozen archive254327bytes SHA2567e3228b293d0737d27a3f3fca57385f5b6c5628cfddf6488ce1c17c1017d619f. Already independently checked in6167016863. Binary archive in same frozen source07e81116 is equivalent.
3. ORIGINAL plan: fetch historical canonical PR58 comment6159620928 via GitHub API and decode its base64 fenced block into a private local original-plan.json. Exactly22468bytes SHA256ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a. Already independently checked in6167232965. Do not publish body/replacements/rendered contents or include them in logs.
4. `reproduce_plan_offline.py` in this supplement is an inspectable convenience aid, not an independent approval. Reviewer may implement equivalent operations themselves.

## Independent reproduction in reviewer's disposable sandbox

Read and inspect the aid plus the four frozen helpers and renderer before running. Unlike the earlier DATA-ONLY archive verifier, this aid EXECUTES AUDITED OFFLINE COMPILER/RENDERER FUNCTIONS. It never calls host driver, main routines, install(), service operations, network or a production path. It writes only safe checked file names under a temporary directory and deletes that temporary directory afterward. Do not run it on the UK host.

```
python3 -I -B reproduce_plan_offline.py \
  --old-archive original-102-runtime-archive.base64.txt \
  --new-archive epoch3-recovery-kit.base64.txt \
  --original-plan original-plan.json
```

Both archives may be binary or Base64. Aid checks exact archive hashes/sizes before bounded decompression, rejects unsafe names/duplicates/nonregular members, verifies old/new102 actual file hashes andkit hash. Only102runtime+manifest files are materialized for each root. Four helper definition modules are loaded under non-main names from hash-checked kit bytes: build_epoch3_runtime, inspect_epoch3, prepare_epoch3_bindings, epoch3_plan. Their main operations are never invoked. The pinned identity renderer is loaded by the audited binding function, also under a non-main name.

Actual audited `proposal()` verifies all24 original rendered hashes before calculating new24. `compile_plan()` rebinds3plugin references, activation/dispatcher/TLS. Aid then separately checks each newsource/rendered hash,3plugin references, preservedcanonicalidentity,proposedPREPARED4,TLSrelease/hash, and canonical plan digest0966ab156508228670faaadbba97ff62e19dac8451cced3598eda4eb0bea7f76.

Source-owner local fullinput run succeeded using Python3 and Python3.6.8;3payload mutation cases rejected (old archive,new archive,originalplan). Base64 whitespace is intentionally normalized and is not a payload mutation. These source-owner results demonstrate reproducibility only. Reviewer must execute their own check and record result. Prior UK39 and fullpreflight remain separate; do not rerun unaffectedUKtests.

## Final decision must cover all boundaries together

- Prior independently closed B1/archive/tree/old102baseline/originalplan integrity are retained.
- Finish24-target/3plugin/canonicalplan reproduction above, inspect remaining semantics, and give one exact fullscope decision or all remaining blockers together.
- Failure policy FENCE_STOP_RETAIN_NO_REPLAY is finite partial-state containment: revokeactivation,attemptfixedstops/allcleanupgroups,preserveevidence,HOLDunknown. It does NOT undo every provisioning side effect. Manual reconciliation may be needed. Owner explicit acceptance of this boundary is pending at publication; broad priorauthorization is not recorded as a new answer.
- Exact newapproval required; historical grants consumed. Noautomaticretry,oldwriterrestart,historynotificationreplay.
- RealACME/HTTPS/notificationACK/P2-P3E2E remain post-admissionPENDING. Review reproducibility is not production acceptance.
- Frozen kit unchanged; no source refreeze, no newqueue, no servercommands required to complete this review.
