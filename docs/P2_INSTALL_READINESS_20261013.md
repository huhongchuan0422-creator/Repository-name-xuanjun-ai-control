# P2 installation readiness — 2026-10-13

P2 source/outcome owner: WORK_NATIVE. Same PR49/parent task; ChatGPT source stopped per PR17 comment6136396455 and retains tasks4/5. Dots retains its registered scopes. No runtime execution authority is inferred from source ownership.

## Current frozen source

- commit: 46a7c6796f61c6f196eb1d95497f2fb94e22fc00
- tree: 4c58232c60a7f397370bab5c43631ea84adeda72
- artifact: 11786072168
- tar SHA256: 25999a0491a94ce8b9c1c24262ccba38bdfc737e32193ae2825c7de9202a205b
- manifest SHA256: 9c8ded6c3c17c88e76361085b8ee752f997d947c51506656099b22e033777d4c
- files:77
- source regression38339139876 and freeze38339139836 SUCCESS; actual80 Python tests plus Node checks.
- same-artifact mechanical QA/Security38339218158 SUCCESS.
- UK Python3.6.8 verify-only38339220772 SUCCESS; actual17+16=33 regression tests.
- exact-artifact pregate38339223129 SUCCESS.

Supersedes artifact11784412668/source df06290d for current boot-lifecycle bytes. Independent source/release approval remains required. These are isolated tests and installer verify-only, not installed reboot/socket/E2E acceptance.

## Source corrections

Complete post-open fd cleanup; bounded scan slices with activation/inode-bound cursor in existing canonical events; finite sweep upper ID and restart progression; Gateway-only exact-backup restoration after ACTIVE while old coordinator remains masked; Gateway starts before relay/dispatcher; existing OAuth reference verified read-only with16MiB cap rather than1MiB. No credentials copied. Normal rollback still restores original unit files without automatically restarting old writers.

## Measured prerequisites

Evidence: UK read-onlyfacts38336367068/job115097248332 at collector commit9f22c0012a74db683046819cac6d4bf3310ecd4b. Scope is those exact fixed paths/time; absence does not prove no equivalent exists elsewhere.

| Prerequisite | Observed | Required next action |
| --- | --- | --- |
| gh binary | Host fixed paths remain absent. Official v2.102.0 staged artifact11784779205; binary SHA256 7469124f706944133d6a169691dd1c6c3511b12e85878d255e044e2948df4c9b. Hosted and UK offline exact version PASS at run38337815855/job115101842365 | Preparation compatibility closed; independently review and bind staged source to existing prerequisite plan before Owner installation |
| Existing OAuth reference | existing private5MiB-class store under xuanjun_dev | Re-read exact identity/hash just before preflight; no copy and no exposed value |
| GitHub intake token | /etc/xuanjun-development/github-intake-token absent | Existing protected enrollment must supply scoped token; ephemeral CI token is not persistent service auth |
| Owner dashboard token | /etc/xuanjun-owner-callback/owner-dashboard-token absent | Protected provisioning/enrollment; do not log secret |
| Owner callback auth/HMAC | owner-callback-auth and owner-callback-hmac absent | Protected provisioning; bind verified receiver and current protocol |
| Owner identity/chat | owner-user-id and owner-chat-id absent | Read verified existing Owner enrollment, never guess IDs |
| HTTPS/TLS | inspected nginx/Caddy binaries/configs and TLS dirs absent; no TLS refs found | Reuse a proven deployed reverse proxy or prepare reviewed TLS provisioning; NOT_APPLICABLE is not public HTTPS acceptance |
| P2 identities/activation | pre-install absent | Existing prerequisite/install transaction creates reviewed isolated identities; installation-created checks remain NOT_RUN until then |
| Boot and rollback persistence | Durable prior enabled/disabled journal added to existing runtime adapter; bound to exact provisioning receipt. Interrupt/restart/drift regressions PASS on hosted and UK | Independent review and installed restart/rollback proof remain required; unsupported persistent states HOLD |

## Retained completion sequence

1. Separate reviewer reads exact current package and consolidated source/lifecycle delta. Work fixes findings; independent Release approval is mandatory.
2. Resolve the measured prerequisites via existing asset/provisioning/enrollment paths. Complete Tokyo/Domestic reuse check before activation; no new registry/queue or OAuth duplication.
3. Render a single concrete plan accepted by packaged validate_plan, with real source/target/owner/mode/source-hash/rendered-hash, units, binary and plugin bindings, canonical activation identities and rollback paths. Validate all values; missing data is HOLD. Bind canonical plan bytes to SHA256. No placeholder root command is install-ready.
4. Stage the reviewed exact package and root-protected plan/transaction directory. Use only packaged scripts/uk-p2-install.py operations verify-only/install/rollback with that digest. Installation remains Owner manual node under current policy.
5. Prove installed hashes, socket activation identity, dispatcher-UID preflight, canonical WAL/epoch/single-writer, outbox delivery ACK, restart and rollback. Then actual E2E under its separately admitted scope. Preserve f998 unknown-effects no-replay boundary.

Current: SOURCE_TESTED_INSTALL_PREPARATION_HOLD. P2_RELEASE_GRANTED=NO; P2_INSTALL=NO; real installed socket/service/rollback/E2E=NOT_RUN. Work retains outcome responsibility and continues independently executable preparation; these gaps are not a request to rerun old package review.

## Pinned gh preparation receipt

Workflow source e4e7a5d7876be791377a4a332feb4fd093c222b0; run38337815855 both prepare and uk-compatibility SUCCESS. Actual UK job log confirms exact binary digest and gh version2.102.0. Downloaded only official archive with pinned SHA256 bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386; extracted only bounded regular bin/gh, checked ELF64 x86_64. UK probe used temporary directory, isolated HOME and minimal environment; cleanup completed, no root/service/credential/API/model action. MODEL_CALLS=0; INSTALL_PERFORMED=NO. Artifact11784779205 zip digest73299316ceda96c292bde0a7d1aa44f2b56de10ab6d17b3123dbc9785727af86. Its hosted receipt says UK NOT_RUN because uploaded before downstream UK job; this downstream exact-binary receipt supplies compatibility evidence without editing old artifact. Host target /opt/xuanjun-runtime/gh/gh remains absent. P2 package11784412668 unchanged, release/install remain NO.

## Existing Codex exact version receipt

Corrected collector source35db390793b48ae918024de1aac47e926b600a7f; UKrun38338195353/job115102994438 SUCCESS, actual logs read. Both pinned candidates hashed before and after non-root xuanjun_dev --version execution with minimal environment/HOME=/nonexistent; no inference/API/model call. Existing standard candidate is codex-cli0.158.0 (SHA256167c0148a849d2444f1b5a7fb5f8bb2de1de5ae13a2a504b833fc765980f5cd9), so cannot use it as0.160.0. Required0.160.0 is /home/xuanjun_dev/.openclaw/npm/projects/openclaw-codex-8902d781d4__openclaw-generation__g-d803e8e002e42fe5/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex (SHA25612eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad, owner1002:1002, mode0700, size289101384). The latter can be explicitly bound as reviewed prerequisite source for fixed target /opt/xuanjun-runtime/codex-0.160.0/codex; no copy/install performed. First collector run38338072001 failed syntax before execution and is superseded only for this version probe. Protected credentials/OwnerIDs/TLS/boot rollback and independent release remain unresolved.

## Boot lifecycle delta

Before Gateway/service starts, after ACTIVE descriptor, persist all fixed units and reused Gateway prior enabled/disabled states using existing fsynced transaction receipt primitive. Enable and verify each unit. Rollback validates journal, exact provisioning digest and every current state before changing enablement; restores original persistent states, including preserving originally enabled Gateway. ENABLE_REQUESTED survives partial failure/process loss; RESTORED rejects activation reuse. Unsupported masked/runtime/static states HOLD. Source fixture and UK temporary-directory tests do not prove actual reboot. No installation performed.
