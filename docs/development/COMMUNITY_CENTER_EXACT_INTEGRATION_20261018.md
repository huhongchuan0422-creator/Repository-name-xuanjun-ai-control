# Community / website Center exact-source integration

## Source and authority

This is an offline source candidate, not a production installation, independent review, payment authorization, or live acceptance. Existing Identity, Tenant, CRM, RBAC, sessions, project grants, encrypted object storage, scanner boundary and database remain authoritative. No parallel identity system or business policy was introduced.

Website source: `feature/work-pr122-site-hub-integration-20261016`, exact commit `15c263e65f42cce18828a81bfc261e48c94636c7` in `huhongchuan0422-creator/Repository-name-xuanjun-ai-control`.

Community baseline: `d9dda1bfff5d19b30033e24725d0df269a233ad4`.

Explicit core pin transition:
- Previous SHA-256: `f9a736fa954bcc3fbdf2eea317bb0b71559864126c940ac6738a4bc9e4a87bd4`
- Integrated SHA-256: `cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0`

The three existing community adapter pin checks and their regression assertions now bind the exact website core. The core and its three upstream dependencies are copied without modification. Git blob SHA and SHA-256 for all six imported files are recorded in `COMMUNITY_PINNED_DEPENDENCIES_20261017.json`, including previous pins. `pr122_customer_source.py` and `pr122_customer_runtime.py` are byte-identical to their previous community versions.

## Actual compatibility change

The upstream core adds `message_evidence`, `project_activity_evidence`, and `privacy_receipts` to its existing encrypted Center database. It captures message provenance, material/change/delivery evidence and privacy request receipts. Existing project and message access now includes upstream evidence-integrity and subject-drift guards. Message and checklist reads gain upstream transactional audit behavior. Optional evidence/privacy context callbacks remain protected server configuration; absent historical context stays unknown.

Dependencies are the exact upstream `pr122_customer_evidence.py`, `pr122_customer_activity_evidence.py`, and `pr122_customer_privacy.py`. The deterministic offline package now includes and requires all six Center files; missing a dependency fails packaging. No new routes, grants, scanner, outbound transport, host actions or runtime installation were added.

## Executed synthetic verification

- Existing community suite: 565 tests executed; 538 passed; 27 environment errors; no assertion failures. This run began before the new integration test file was collected.
- All 27 errors were environment limitations: 10 AF_UNIX socket operations denied with EPERM; 17 browser launches blocked by missing Playwright browser binary or sandbox socket restrictions. They remain unverified and require the existing hosted workflow. Tests and sandbox permissions were not weakened.
- Existing private project-material HTTP and permission journey: 11 passed.
- Existing merchant onboarding journey: 15 passed.
- New exact-source, package-closure and shared-identity/evidence tests are in `test_community_center_version_contract.py`; their final result is recorded by the parent final-source run.
- A separate synthetic upgrade loaded the exact previous core SHA above, registered a verified fixture account, imported signed fixture CRM authority, created an existing session and message, closed the old database, then opened it twice with the exact new core. Both passes preserved account/session/project/message identity, produced exactly one legacy message evidence record, kept consent context null, and passed core integrity verification. The only new tables were the three upstream evidence tables. No production database was accessed.

## Release and recovery boundary

Local source compatibility does not prove production migration or rollback. Upstream installation performs additive DDL and backfill on first Center open. Before any authorized production installation, take and verify the existing database/object backup and use the existing release/rollback gates. Do not treat swapping the Python core back alone as a tested database rollback. Independent review, hosted browser/Unix proxy checks, deployment and real operational acceptance remain separate requirements.
