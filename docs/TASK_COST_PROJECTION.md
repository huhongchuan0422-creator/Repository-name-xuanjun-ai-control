# Task cost projection — V2.7 1.9/1.10 source preparation

WORK owns the isolated source scope registered on PR17 comment6136253099.
`project_costs(task_id, records)` is a pure display utility, not an accounting
ledger. The caller supplies an authenticated complete component inventory from
the existing canonical cost source. The module cannot discover omitted costs;
VIEW_READY means supplied records are internally consistent, never financial
completeness or commission eligibility.

Each record has exactly task_id, component_id, currency (three uppercase letters),
kind (ACTUAL/ESTIMATE/UNKNOWN), amount_micros (nonnegative integer or null), and
evidence_sha256 (lowercase SHA256 or null). UNKNOWN requires both null. Monetary
unit is one millionth of the stated currency. No currency conversion is performed.
One component/kind is unique; identical duplicates collapse, conflicts reject.
Actuals and estimates aggregate separately per currency. Missing amount/evidence
poisons that category's total to null; unknown actual components poison actual
total. Estimates never become actuals. Explicit evidenced zero is preserved.
Missing categories and empty input stay incomplete. Malformed input rejects.

Caller verifies evidence authenticity, its task/component/currency binding,
coverage, pricing authority and actual versus estimated classification. A hash
format alone does not prove any of these. Refunds/credits must be reconciled by
the existing financial ledger; negative input is rejected here. This scope does
not compute revenue, gross profit, recommended commissions or payments.

Integration requires the existing dashboard/ledger owner, independent review,
complete component mapping and lifecycle tests. No DB, network, model, persistence
or runtime permission is added. UK integration/install/acceptance NOT_RUN.
