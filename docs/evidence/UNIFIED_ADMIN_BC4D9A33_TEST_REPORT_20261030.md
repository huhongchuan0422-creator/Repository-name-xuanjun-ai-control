# Unified Admin bc4d9a33 Test Report

## Frozen source

- Commit: `bc4d9a3383d04bd39590cfc083981c2c317580e7`
- Tree: `43d6484cd0da324f0e32c2970249f300e59ce0ee`
- Scope: unified admin read-only projection and Owner Workbench hosted adapter.
- Deployment: `NOT_EXECUTED`
- Production connection: `NOT_EXECUTED`

## Recorded commands and results

The following results are copied from the original tool receipts for the
frozen revision; they are not browser or production claims.

```text
python3 -m unittest tests.test_unified_admin_projection tests.test_task_center_app tests.test_task_center_session_auth
```

- Result: `24 tests OK`
- Failures: `0`

```text
node demos/owner-workbench-v2/tests/workbench.test.cjs
```

- Result: `38/38 ok`
- Failures: `0`

Independent journey/contract/projection regression command:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_task_center_full_journey tests.test_project_delivery_contract tests.test_digital_twin_projection
```

- Result: `18 tests OK`
- Failures: `0`

```text
git diff --check
```

- Result: exit code `0`

## Browser boundary

- Browser action: OpenClaw browser `action=start`
- Browser execution: `BLOCKED`
- Chrome stderr: `libatk-1.0.so.0: cannot open shared object file`
- Screenshot, visual E2E, hosted deployment, customer acceptance and
  production acceptance: `NOT_EXECUTED`.
