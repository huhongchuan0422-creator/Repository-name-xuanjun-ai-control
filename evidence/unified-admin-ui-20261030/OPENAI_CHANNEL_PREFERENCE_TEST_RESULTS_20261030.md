# OpenAI manual channel preference — test evidence

- Observed at: `2026-10-30 18:01:07 +0800`
- Base commit: `a61a7e1c39a7ed72d5b5037278c1f6f2cf7fdaaf`
- Scope: manual `API_FIRST` / `SUBSCRIPTION_OAUTH_FIRST` selection,
  server persistence/readback, fail-closed resolution, Codex intent binding,
  and bounded promotional-credit admission.
- Real model/API calls: `NONE`
- Production install/mutation: `NONE`
- Automatic fallback/recharge: `DISABLED`

## Final passing commands

### Connection and quota gates

```text
python3 -m unittest -v tests.test_connection_management \
  tests.test_codex_execution_adapter.CodexExecutionAdapterTests.test_recent_verified_openai_promotional_credit_is_explicitly_admitted \
  tests.test_codex_execution_adapter.CodexExecutionAdapterTests.test_available_but_not_included_or_free_quota_is_rejected \
  tests.test_codex_execution_adapter.CodexExecutionAdapterTests.test_test_only_quota_on_known_paid_provider_is_rejected
```

Raw summary:

```text
Ran 12 tests in 5.134s

OK
```

Count: `12 passed / 0 failed / 0 skipped`, exit `0`.

### Projection, HTTP read/write/readback, and Codex binding journey

```text
python3 -m unittest -v tests.test_unified_admin_projection \
  tests.test_task_center_app.TaskCenterAppTests.test_manual_openai_channel_preference_persists_and_reads_back \
  tests.test_task_center_app.TaskCenterAppTests.test_workbench_host_and_admin_projection_are_read_only \
  tests.test_task_center_full_journey.FullJourneyTests.test_project_to_model_to_independent_review_acceptance
```

Raw summary:

```text
Ran 9 tests in 2.069s

OK
```

Count: `9 passed / 0 failed / 0 skipped`, exit `0`.

### Workbench UI candidate and hosted controller

```text
node demos/owner-workbench-v2/tests/workbench.test.cjs
```

Raw summary:

```text
tests: 40 passed, 0 failed
```

Count: `40 passed / 0 failed / 0 skipped`, exit `0`.

### Full affected Codex regression

```text
python3 -m unittest -v tests.test_codex_execution_adapter
```

Raw summary:

```text
Ran 24 tests in 2.361s

OK
```

Count: `24 passed / 0 failed / 0 skipped`, exit `0`.

### Full affected Task Center HTTP regression

```text
python3 -m unittest -v tests.test_task_center_app
```

Raw summary:

```text
Ran 12 tests in 7.073s

OK
```

Count: `12 passed / 0 failed / 0 skipped`, exit `0`.

## Repaired first-run findings

The first affected run was not reported as passing.  It found:

- read-only projections constructed with `__new__` had no `clock` attribute,
  causing two HTTP projection errors;
- two JavaScript assertions still expected the previous completely read-only
  copy and rejected the new bounded action/correct negative wording.

The source and assertions were corrected, then every affected command above
was rerun to a passing terminal result.

## Proven boundaries

- Owner selection and actual effective channel are distinct fields.
- A missing, inactive, expired, or ambiguous selected channel resolves to
  `effective_channel=NONE` and never chooses the other channel.
- Preferences are tenant-bound, admin-only, version-fenced, audited, and
  persisted in the existing connection database.
- Codex intent creation binds the resolved `connection_id/provider_id`; a
  conflicting caller-supplied binding is rejected.
- Known-paid API transport is admitted only for a recent explicit
  `OPENAI_VERIFIED_PROMOTIONAL_CREDIT` quota receipt.  Generic metered
  eligibility and TEST_ONLY free claims on paid providers remain rejected.
- This does not attest that any specific OpenAI call is covered by promotional
  credit.  Official rules and actual billing remain authoritative.
- No credential or secret body appears in projection, UI, logs, or evidence.

## Not executed

- Real OpenAI API call
- Real subscription OAuth call
- Official billing/credit verification
- Browser screenshot/E2E on a real browser runtime
- Hosted or production installation
- Independent audit
