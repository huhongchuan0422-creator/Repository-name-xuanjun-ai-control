# TC477 frozen installer delta: a8a72185

Runtime source: a8a72185ed6164beaf2f8691cca9d682aed5e6e3.
Derived from original 5a05 archive 5b0ce602042cf92cc5fcecebd87291be53f91cb3e5b003fd2b6bb3a0fede2e01.
Only scripts/task_center_handoff_launch.py changed; 46 payloads are byte-identical.

- Archive: 26c98cb9a2d7673e42e3bbc2c48d2e1c6cdec252ff2f0a4c84908c84256edb19
- RESULT-FILES.json: 57b7f34b3aaa2b43e6bd5b229ed7ab164c4cd5adb245ac785a97dbd3d06f6af5
- Before installed manifest: 15ecfa38228e106dc9b8528e98f5b32e9f7d92e67284c71cc1ab521f22091ac6
- 47 files; delete_files empty; all before selectors/modes unchanged.

Use this exact archive, not the superseded 5b0ce602 archive, in the original
carrier installer's stage/verify/rollback procedure. No whole-tree replacement.
No installation or service configuration change has been performed here.

The reviewed launcher entry remains scripts/task_center_handoff_launch.py with
--handoff-runtime-config-file followed by the original app arguments. Config is
service-owned 0600; no secret bodies or arbitrary provider loader. A trusted
host may import main and supply its existing identity_backend/evidence objects.
Enabled CLI without that backend must exit69 with
FORMAL_IDENTITY_BACKEND_UNAVAILABLE before opening a DB. Disabled mode retains
the original TEST_ONLY entry and unavailable handoff; neither is COMPLETE.

Only package binding was rechecked. The a695 independent clean-3.11/no-crypto/
no-PYTHONPATH failure-point PASS is reused for the exact updated launcher SHA;
old 16a/5a05 nonchanged tests and original installer dry are reused, not rerun.
This distribution commit is not a new runtime source revision or self-approval.

Preserve the old archive as evidence, the current 15ecfa38 release, original unit,
configuration and carrier state for recovery. Code reversal is not DB/external
side-effect rollback; the reviewed Supervisor initialization may write schema
if an authorized later startup occurs. Formal backend, receiver/supervisor
identity authority, protected recover/reacquire consumer and custody remain
independent OPEN dependencies. Do not deploy the old archive or fake grants.
