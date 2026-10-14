# P2 hosted runtime checkpoint CI

FEATURE_ID=P2_RETAINED_RECOVERY; same PR17/PR58 work. This checks only the exact
107-file runtime and72 required process/ledger cases, not the complete recovery
kit or UK installation. No self-hosted runner, credentials, models or host effects.

First actual attempt bb85ac136b8e53c2ea32b34d6e69a94360325e28:
- Runtime run38613539870/job116022707474 FAILURE:72 tests ran,2 failures5 errors.
  Hosted toolcache Python is group-writable, so the genuine executable-safety
  check correctly rejected the test fixture before spawning.
- Feature run38613539721/job116022704749 FAILURE: checker7 cases passed, registry
  failed MISSING_TEST_REFERENCES because references must start tests/.

Fixes are test/workflow/registration only; runtime remains source101b465c:
- Private0500 wrapper execs the current Python interpreter in fixture tests.
  Production executable ownership/mode/hash checks are unchanged; no skips added.
- Added real tests/test_p2_runtime_process_checkpoint.py, which executes all72
  cases in an isolated child and rejects skips or reduced discovery.
- Registry now references that real tests/ wrapper; workflow invokes it.
- Local checker and isolated wrapper72 cases pass on3.6.8. Original failed CI
  logs retained. New hosted outcome requires actual run/log readback.

Final test-only followup adds two deterministic deadline/expired-reap checks.
Required count is now74 (23 process,10 Gateway,41 ledger). Runtime source and
30-second production command budget remain unchanged. Subsecond fixture budgets
were replaced with finite1s timeout/3s normal-test budgets to avoid conflating
host scheduling delays with specific injected errors. Earlier timing failures
remain evidence; scheduling pressure is plausible but was not measured. Cleanup
UNKNOWN is never treated as runtime success; test teardown independently proves
owned process termination within a separate bounded harness budget.
