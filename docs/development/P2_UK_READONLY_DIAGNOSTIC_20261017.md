# P2 UK read-only diagnostic phase 1 (PR17)

## 1 Design

Scope is one fixed exact 1771-byte shell command (SHA256 523f3ba132b94efec8bf81980d9db96e083e4779628a29b6540a8bcee67d2794) from PR17#6233805257. It may read only fixed host identity, Python/cgroup, root-installed script stat/hash, four fixed systemd units and three fixed SQLite file metadata paths. It does NOT inspect Writer/epoch/Lease/Fence/trust/in-flight InvokeId; output UNKNOWN is mandatory for those fields. No data or secret reading, installation, environment switching, A5 action or rollback. Command supplied to cloud SWAS must be byte-identical. Approval must be authored by independent auditor account on PR58, bound to protected policy, single Attempt and source pin; it is not yet issued.

## 2 Development

Source is scripts/p2_uk_readonly_diagnostic.py and one-shot integration in scripts/p2_uk_swas_diagnostic.py. The workflow offers read-only-diagnostic and separately approved read-only-diagnostic-query; protected UK job remains manual, fixed actor, independent environment and disabled live switch by default. Existing Git Journal atomic creation, durable CLOUD_DISPATCH_INTENT and UNKNOWN no-redispatch are reused. Stderr is discarded from public logs/artifacts; stdout is published only after bounded strict key/value validation. Any error, timeout, cloud unknown, arbitrary text, duplicate/bad identity or output oversize is HOLD. Never retry RunCommand; only a future fresh query authorization and saved InvokeId may reconcile.

Independent approval Dots and real protected environment, RAM identity, protected journal namespace and current site credentials/Writer proofs are outside this source-only PR. All site work remains HOLD. Offline negative tests tests/test_p2_uk_readonly_diagnostic.py plus inherited 102 tests run in GitHub Actions, with Python 3.6.15 container compatibility tests; hosted successes are not UK host acceptance.
