# Independent Release review — exact frozen P2 artifact

Decision: **RELEASE HOLD / installation admission denied**. This is a structural release review, not an installation or UK acceptance receipt. Independent Security has returned FAIL; Release cannot override that gate. QA findings supplied by the coordinating reviewer also identify absent live native-provider wiring; final QA report remains required.

Reviewed identity: source commit `f840b2e98724a9e5b940f73606ee0687b6ba98c8`; tree `2810ad1e2c596796469c75999f8d1d62ecb74d2d`; archive SHA256 `456ae23aa52e300021c9fb889df84d8eba34965769ce868e5ee6e43c29911a13`; manifest SHA256 `4f77c7f11be7a3c96ecbd8c30c239189876a42a47e9d16cec0f875b8df3b16aa`; export run `38250045267`, artifact `11747942678`. Review reads this unpacked package and its provenance; no original repository history repair is claimed.

## Blocking release conditions

1. **Security FAIL on the exact artifact.** `SECURITY_REVIEW.md` records manufactured execution attestation, registry absence promoted to stopped/no effects, and assistant JSON promoted to authoritative result. These defeat sole-writer and result provenance guarantees. A frozen archive with reproducible hashes is not proof that its execution contract is safe.
2. **Runtime native wiring absent.** `stage1/development_service.py:21,337–367` imports and constructs `CodexAppServerWorker`. Shipping `native_child_adapter.py` in the manifest does not connect it to the installed dispatcher. Release cannot accept a claim that the existing OAuth native provider is operational on this artifact.
3. **No reviewed target-host plan or verify-only receipt is present in this review set.** The CLI requires exact root-protected plan bytes, plan digest, receipt path, transaction directory and fixed release-installer path (`scripts/uk-p2-install.py:34–43,62–88`). The package provenance lists operation names, not those complete reviewed values. The CLI's `verify-only` branch (`89–99`) validates the plan and runtime references but does not call the immutable release installer or its package verification, and it acquires/creates an installation lock before reporting `effects:0`. Such output must be scoped as preflight, not immutable-package verification or a strictly side-effect-free test. No mode was executed in this review.
4. **Same-artifact release chain incomplete.** There is no QA PASS + Security PASS + Release PASS for these hashes, and no production/native E2E or target-host rollback rehearsal evidence in this review set. Earlier package approvals must not be carried over.

## Contracts retained, with limits

- `P2_PACKAGE_PROVENANCE.json` binds source commit/tree, manifest digest, runtime file digests and verifier digest. Independent Security reports archive/manifest/payload integrity and bounded archive-path checks PASS. These establish byte identity, not deployment readiness.
- `p2_install_entrypoint.py:253–325` orders preflight, immutable release staging, runtime provisioning, activation preparation, legacy quiescence, database reopen, ACTIVE transition and service start; failures enter journaled rollback/HOLD. This structure is useful but does not fix the native execution proof defects.
- Rollback (`p2_install_entrypoint.py:191–248`) requires the exact COMPLETE install receipt and active identity, fences the activation epoch before stopping the new runtime, restores provisioning and legacy files, and deliberately does not restart the legacy writer. Package rollback map explicitly requires database/epoch reconciliation before any restart. No actual host rollback was exercised here.
- Existing OAuth/TLS are references; the package declares no credential/private-key inclusion and no new paid API usage. No credential contents were read by this reviewer.

## Minimal required follow-up

Preserve this frozen candidate for audit; do not install or relabel it approved. Repair only the proven native identity/state/result boundary and actual dispatcher/notifier wiring, preserving unknown effects until authoritative reconciliation. Freeze a new exact candidate, bind a complete reviewed fixed-host plan and installation/verification/rollback arguments to that candidate, and run independent QA, Security and Release against the same bytes. Clearly distinguish package integrity, plan preflight, runtime activation and production E2E receipts. Do not broaden architecture or replay an effect-unknown invocation.

Review scope: read-only source/provenance inspection; this report is the only new artifact authored by this reviewer. No package code edits, installer/provider/native/model calls, host changes, canonical ledger changes, leases, fences or epochs were performed.
