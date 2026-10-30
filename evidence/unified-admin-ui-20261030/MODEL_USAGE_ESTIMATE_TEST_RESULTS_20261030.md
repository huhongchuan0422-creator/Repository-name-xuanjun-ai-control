# Model usage estimate increment — raw test results

- Observed at: `2026-10-30 16:53:21 +0800`
- Scope: existing ModelControl usage projection to unified-admin TEST_ONLY read-only UI
- Boundary: model estimate only; not Finance ledger, actual charge, payment, or currency assertion
- Model/API calls: `NONE`
- Production mutation/install: `NONE`

## Python projection

Command:

```text
python3 -m unittest -v tests.test_unified_admin_projection
```

Raw result:

```text
test_builds_read_only_fail_closed_projection (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok
test_disconnected_sources_expose_exact_gaps_without_claiming_connection (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok
test_existing_secret_mask_implies_configured_without_leaking_mask (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok
test_model_usage_is_read_only_estimate_not_a_finance_fact (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok
test_rejects_production_or_cross_tenant_sources (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok
test_secrets_are_reduced_to_status_and_reference (tests.test_unified_admin_projection.UnifiedAdminProjectionTest) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.001s

OK
```

Exit code: `0`. Count: `6 passed / 0 failed / 0 skipped`.

## Workbench JavaScript

Command:

```text
node demos/owner-workbench-v2/tests/workbench.test.cjs
```

Raw terminal summary:

```text
tests: 39 passed, 0 failed
```

Exit code: `0`. Count: `39 passed / 0 failed / 0 skipped`.

The command emitted 39 individual `ok - ...` lines before the summary. The
changed assertion is `hosted mode uses same-origin session and projection
without fixture fallback`, which now verifies the model usage/estimate table
and the non-billing boundary.

## Same-origin HTTP workbench endpoint

Command:

```text
python3 -m unittest -v tests.test_task_center_app.TaskCenterAppTests.test_workbench_host_and_admin_projection_are_read_only
```

Raw result:

```text
test_workbench_host_and_admin_projection_are_read_only (tests.test_task_center_app.TaskCenterAppTests) ... task-center-app: GET /workbench/
task-center-app: GET /api/admin/workbench
task-center-app: GET /api/admin/workbench
task-center-app: POST /api/admin/workbench
ok

----------------------------------------------------------------------
Ran 1 test in 0.645s

OK
```

Exit code: `0`. Count: `1 passed / 0 failed / 0 skipped`.

## Not rerun

The previously accepted unchanged `25 Python / 39 JS / 18 regression`
evidence for commit `58750f7b9812f41901ed91a2b7bf66d1c273e404`
was not presented as evidence for this increment. Only affected tests above
were executed. Independent audit, browser E2E, hosted install, production
install, and customer acceptance remain `NOT_EXECUTED` for this increment.
