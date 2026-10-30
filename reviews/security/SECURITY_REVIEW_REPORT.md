# P3 lifecycle corrected candidate — independent Security review

## Result

**PASS for the reviewed local host-boundary increment at the exact fixed Git
artifact.** No business-code, test, expected-result, install, host, service,
external-system, or site changes were made by this review.

- Commit: `875121c4e329ae47650b66a9a3b9c28ba4f1574b`
- Tree: `6422b209c22e353914fb06733ea44b0db9b8ad48`
- Manifest SHA-256:
  `c38e0dda4f1db500b8525ab5b57012c53492ac71b02dc8ab4e02447f084f32e7`
- `SHA256SUMS` SHA-256:
  `399ddb7d0af29d5141254afdde5152f288e1dbb885950c7a676b93c9e995722e`
- Source SHA-256:
  `aa06589ab51298cd64ecd4ac8bb9af8746c692e6db7205da191ce7c718dfb17f`
- Deterministic `git archive --format=tar HEAD` stream SHA-256:
  `a13d95b2a69117ebe3d31147ef2b2a564e263330684089e55015fc2cf116a0fc`
- Independent checkout:
  `/home/xuanjun_dev/p3-lifecycle-independent-security-20261031/checkout`
- Runtime: Python 3.6.8

This scoped PASS is not Hosted CI, installation, deployment, field execution,
P2 acceptance, P3 release, or business acceptance.

## Identity and writer-stop preflight

At `2026-10-31 00:42:51 CST`, the candidate and detached independent checkout
were both clean and resolved to the Commit/Tree above. A no-index source diff
between them was empty. Process and `/proc/*/cwd` inspection found no live
Writer or test process bound to the candidate; only the inspection command and
its `rg` process appeared in the process scan. The independent checkout stayed
clean after all tests.

`sha256sum -c SHA256SUMS` verified all 22 listed candidate members. Git object
inspection completed; one unrelated dangling blob was reported and does not
belong to the reviewed Commit/Tree.

## Security properties reviewed

1. **STARTED fence binding — PASS.** Receipt verification first binds the exact
   receipt subject. The STARTED payload fence must then equal that subject fence
   before the original supervisor can be invoked. The mismatch counterexample
   passed and the supervisor call count remained zero.
2. **Completion full lineage — PASS.** Completion requires equality across all
   acceptance/recovery run-subject keys (`task_id`, spec, artifact, run,
   session, fence, epoch, generation, resume generation). The recovery payload
   must additionally repeat the verified receipt subject fence and remaining
   lineage values. Cross-run and payload-only fence changes were rejected.
3. **Runner launch/resume uncertainty — PASS.** After either adapter call has
   happened, malformed or tampered ACK evidence returns
   `UNKNOWN_RUNNER_EFFECT_HOLD` with `automatic_retry=false`. Independent probes
   observed exactly one launch call and exactly one resume call, with no retry.
4. **Outbox send uncertainty — PASS.** Malformed/tampered post-send evidence
   returns `UNKNOWN_NO_REDIAL` with `automatic_retry=false`. The independent
   probe observed exactly one send call and no redial.
5. **Caller-asserted authority rejection — PASS.** A caller-supplied admission
   argument claiming authorization could not override a host-reader proof with
   `execution_authorized=false`; rejection occurred before adapter invocation.
   Receipt trust also requires the injected `TrustedReceiptProvider`, exact
   envelope/subject/kind, and checksum verification.
6. **Default-off and exact-shape behavior — PASS.** Execution and notification
   boundaries remain default-off; the supplied suite confirms failures occur
   before adapter/transport calls and that same-artifact independent roles and
   exact evidence shapes are required.

No source-security defect was found in the requested review scope.

## Independent test and probe results

- Original supplied suite: **21/21 PASS**, 0 failures, 0 errors, 0 skipped.
- QA counterexamples: **5/5 PASS**, 0 failures, 0 errors, 0 skipped.
- Combined discovery: **26/26 PASS**, 0 failures, 0 errors, 0 skipped.
- Additional Security semantic probes: **8/8 PASS**.
- Candidate checksum members: **22/22 verified**.

Raw evidence:

- `PREFLIGHT_RAW.log`
- `ORIGINAL_21_RAW.log`
- `COUNTEREXAMPLES_5_RAW.log`
- `COMBINED_26_RAW.log`
- `SECURITY_SEMANTIC_PROBES_RAW.log`
- `ARTIFACT_INTEGRITY_RAW.log`
- `R1_TO_R2_DIFF_RAW.log`
- `GIT_OBJECT_AUDIT_RAW.log`

## Remaining integration and release gates

Security approval is limited to this inert local increment. It does not admit
installation or any real side effect. The following remain required and
unverified: real P2 field acceptance; explicit P3 release; current canonical
ledger/descriptor/task/spec identity; proof of a sole Writer and old-Writer
stop; approved host runner/provider/outbox/watchdog implementations; immutable
real ACK/STARTED/progress/stop/completion receipts; Hosted CI against the same
artifact; release approval; and two consecutive real tasks with matching QA,
Security, and business receipts.

B7 remains blocked until B6 is actually `COMMITTED` and a same-instance fresh
query satisfies `B7_ENTRY_GATE.md`. This Security result grants no CP14/15/16,
root, service, credential, network, notification, installation, or production
authority.
