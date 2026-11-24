# Internal test reapply seam (candidate only)

Base: 193627c0b5c57f38a290db56cfcb536dc0479c4a. No runtime install.

Original /merchant/onboarding authenticates the existing Center session/CSRF.
New reapply_preview / reapply_release accept only application, expected_version,
idempotency_key. The existing reviewer/project authority is rechecked under
BEGIN IMMEDIATE. Protected Python reapply_authority composition is absent by
default. HTTP cannot supply targets, financial_clear, provider or Dots effects.

The adapter constructs the existing Policy/Snapshot planner types from protected
exact-two-test grants, the current reader identity and the original Center
application/record/verified observation/account/history. Reconciled scope and
external effect facts must be supplied by the existing authorized custodian, not
invented from two FINISHED candidates. No account/schema/provider framework.

Release writes only encrypted original application metadata and original audit
in one Center transaction. Old onboarding/records/observations/openings, orders,
callbacks and login identities are retained. CAS/trusted receipt replay uses the
original planner. New draft attaches to the released current-generation cursor
inside the original save transaction; errors roll back both. Old generation is
read-only. Mini selection honors current_cursor rather than sorting the old
FINISHED/APPROVED application back to current. New generation provider mismatch
is rejected; no old result is copied into the new application.

The original reviewer detail offers preview then explicit confirmation. It
retains the idempotency key after failures, does not send provider/finance facts,
and never invokes wechat_execute/query. Existing fields remain unchanged.

## Scope separation after Owner 00:42 revision
This internal planner/adapter is NOT a WeChat Mini identity unlink command and
NOT a payment authorization unlink. The newly authorized live task concerns only
the uniquely identified test shop's old Mini association, preserving payment
authorization/history/orders and forbidding final submission or provider config
changes. It remains with the original live custodian chain; this code neither
installs itself nor enables policy or performs that action. Real test identity
mapping is not inferred from the synthetic test1/test2 fixtures.

## Direct verification
- tests/test_community_reapply_http.py: synthetic original HTTP/Center transaction,
  preview/replay/CAS, exact targets/scope/epoch, policy injection denial, rollback,
  preserved draft/history/schema, unknown submissions and new provider pollution.
- node tests/community_reapply_delta.cjs: exact original detail action source and
  exact Mini current selection expression, cancel/confirm/failure/stale response.
- Original save/auth/HTTP/failure diagnostic/Mini access tests and original
  history/withdrawal DOM flows are the directly affected regressions.

Runtime for Python tests: existing protected native-test venv in its original
mount namespace, using only isolated synthetic fixture databases and an ephemeral
loopback test listener. No production DB/config/secret read or write. Node tests
use the existing host node. No dependency installs or runtime service changes.

Recovery: uninstalled candidate code can be reverted as a code change only.
Any future metadata transition requires the original receipt and current-version
checks; code rollback alone is not data rollback. Real live operation and
independent review/real-account acceptance remain NOT_RUN.
