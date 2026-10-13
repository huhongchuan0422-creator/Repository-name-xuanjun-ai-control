# P2 installation readiness — 2026-10-13

P2 source/outcome owner: WORK_NATIVE. Same PR49/parent task; ChatGPT source stopped per PR17 comment6136396455 and retains tasks4/5. Dots retains its registered scopes. No runtime execution authority is inferred from source ownership.

## Current frozen source

- commit: df06290d42cb8d80d8886320e075fb479d52cde3
- tree: 119379ffbf4b0632c163ab0945f02294813d99a7
- artifact: 11784412668
- tar SHA256: 08b5fca14490b969fa7deada6ef60b2c865898c782d38454a78bfb0e08dac6cd
- manifest SHA256: b07b5c35e8effe226d5f990d8df57cdc262d64fd264562299a78da522a117e78
- files:77
- source regression38336308019 and freeze38336308006: SUCCESS,76 Python tests plus Node checks.
- same-artifact mechanical QA/Security38336480483: SUCCESS.
- UK Python3.6.8 verify-only38336482564: SUCCESS,17 transaction/pagination/relay tests plus12 lifecycle/reference tests.

The prior7c78f4f0/artifact11784690627 is a historical tested checkpoint. It does not certify the current lifecycle delta. Mechanical checks and author tests do not replace independent source/security/release approval.

## Source corrections

Complete post-open fd cleanup; bounded scan slices with activation/inode-bound cursor in existing canonical events; finite sweep upper ID and restart progression; Gateway-only exact-backup restoration after ACTIVE while old coordinator remains masked; Gateway starts before relay/dispatcher; existing OAuth reference verified read-only with16MiB cap rather than1MiB. No credentials copied. Normal rollback still restores original unit files without automatically restarting old writers.

## Measured prerequisites

Evidence: UK read-onlyfacts38336367068/job115097248332 at collector commit9f22c0012a74db683046819cac6d4bf3310ecd4b. Scope is those exact fixed paths/time; absence does not prove no equivalent exists elsewhere.

| Prerequisite | Observed | Required next action |
| --- | --- | --- |
| gh binary | absent at /usr/bin/gh,/usr/local/bin/gh,/opt/xuanjun-runtime/gh/gh,/home/xuanjun_dev/.local/bin/gh | Select and verify a real source binary through existing prerequisite plan; no fabricated hash |
| Existing OAuth reference | existing private5MiB-class store under xuanjun_dev | Re-read exact identity/hash just before preflight; no copy and no exposed value |
| GitHub intake token | /etc/xuanjun-development/github-intake-token absent | Existing protected enrollment must supply scoped token; ephemeral CI token is not persistent service auth |
| Owner dashboard token | /etc/xuanjun-owner-callback/owner-dashboard-token absent | Protected provisioning/enrollment; do not log secret |
| Owner callback auth/HMAC | owner-callback-auth and owner-callback-hmac absent | Protected provisioning; bind verified receiver and current protocol |
| Owner identity/chat | owner-user-id and owner-chat-id absent | Read verified existing Owner enrollment, never guess IDs |
| HTTPS/TLS | inspected nginx/Caddy binaries/configs and TLS dirs absent; no TLS refs found | Reuse a proven deployed reverse proxy or prepare reviewed TLS provisioning; NOT_APPLICABLE is not public HTTPS acceptance |
| P2 identities/activation | pre-install absent | Existing prerequisite/install transaction creates reviewed isolated identities; installation-created checks remain NOT_RUN until then |
| Boot and rollback persistence | service starts tested only as fixtures; no installed boot proof | Bind boot enablement and prior enable-state rollback in the installation plan and test restart; WantedBy text is not activation |

## Retained completion sequence

1. Separate reviewer reads exact current package and consolidated source/lifecycle delta. Work fixes findings; independent Release approval is mandatory.
2. Resolve the measured prerequisites via existing asset/provisioning/enrollment paths. Complete Tokyo/Domestic reuse check before activation; no new registry/queue or OAuth duplication.
3. Render a single concrete plan accepted by packaged validate_plan, with real source/target/owner/mode/source-hash/rendered-hash, units, binary and plugin bindings, canonical activation identities and rollback paths. Validate all values; missing data is HOLD. Bind canonical plan bytes to SHA256. No placeholder root command is install-ready.
4. Stage the reviewed exact package and root-protected plan/transaction directory. Use only packaged scripts/uk-p2-install.py operations verify-only/install/rollback with that digest. Installation remains Owner manual node under current policy.
5. Prove installed hashes, socket activation identity, dispatcher-UID preflight, canonical WAL/epoch/single-writer, outbox delivery ACK, restart and rollback. Then actual E2E under its separately admitted scope. Preserve f998 unknown-effects no-replay boundary.

Current: SOURCE_TESTED_INSTALL_PREPARATION_HOLD. P2_RELEASE_GRANTED=NO; P2_INSTALL=NO; real installed socket/service/rollback/E2E=NOT_RUN. Work retains outcome responsibility and continues independently executable preparation; these gaps are not a request to rerun old package review.
