# P3 corrected candidate independent QA R2 report

## Result

**PASS for the reviewed local increment at the exact fixed artifact.**

- Commit: `875121c4e329ae47650b66a9a3b9c28ba4f1574b`
- Tree: `6422b209c22e353914fb06733ea44b0db9b8ad48`
- Candidate and protected independent checkout: tracked/untracked clean
- Writer: stopped before QA R2

This PASS is only independent local source/test acceptance of this increment. It
is not Security approval, Hosted CI, installation, deployment, field execution,
P2 acceptance, P3 release, or business acceptance.

## Independent results

- Original suite: **21 run, 21 PASS, 0 failures, 0 errors, 0 skipped**.
- Existing four QA counterexamples: **4 run, 4 PASS, 0 failures, 0 errors, 0 skipped**.
- New completion-fence counterexample: **1 run, 1 PASS, 0 failures, 0 errors, 0 skipped**.
- All counterexamples: **5 run, 5 PASS, 0 failures, 0 errors, 0 skipped**.
- Combined suite: **26 run, 26 PASS, 0 failures, 0 errors, 0 skipped**.
- Independent semantic probe: subject fence `7`, recovery payload
  `current_fence=999`; correctly rejected with
  `COMPLETION_LINEAGE_CHANGED`.

## Semantic and fixture audit

The R2 source adds exactly the missing condition:

```text
payload["current_fence"] == subject["fence"]
```

The new negative regression keeps the verified receipt subject equal to the
accepted subject and changes only payload `current_fence` to `999`. It therefore
exercises the defect found in independent QA R1 directly.

The original positive completion assertion remains unchanged: it still expects
recovery `current_fence=8`. The fixture now uses a single receipt/acceptance
subject with fence `8` for terminal, test, CI, QA, Security, business, and
recovery receipts. Previously its subject was fence `7` while the expected
payload fence was `8`; that data was inconsistent with the corrected contract.
Aligning the subject, without changing the assertion, fixes the invalid positive
fixture and does not weaken the negative gate.

The other existing counterexample bodies and expectations remain unchanged.
STARTED fence binding, mixed acceptance/recovery lineage rejection, launch
uncertainty HOLD/no-retry, and send uncertainty UNKNOWN_NO_REDIAL/no-redial all
remain covered and passing.

## Next gates

Security may review the exact same Commit/Tree. Real P2 field acceptance,
explicit P3 release, active runner/provider/ledger/outbox/watchdog integration,
Hosted CI, installation, and two consecutive real tasks remain external gates.
B7 remains blocked until its independent B6 `COMMITTED` plus same-instance fresh
query prerequisite is actually satisfied.

