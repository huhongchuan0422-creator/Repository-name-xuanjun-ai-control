# B3 → B4 / CP10 finite sandbox — source delivery, UK not executed

Task: PR17 #6284216737. Baseline9892c45d. Inherit actual UK preparation receipt #6284188828; do not rerun B1/B2/CP03/CP04–09. Accepted B3 preparation receipt: `34d1530271efaabb4b65c5c44d2e76bd04258247dfc36a9a613aa829ec18dc8b`.

## Exact implementation and evidence

Validated source Commit `0c09b3ae24fcb3e2697a94ef190337a792bca102`, Tree `5756fee7e7b0e172858af209775637cafcb577c5`.

[Hosted 39377081631](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39377081631): SUCCESS. Python3.11/3.12 each11 targeted tests; exact3.6.8 host API tests3; real two-role Docker CLI roundtrip; actual host main including new-directory UID1002 ownership, both role containers, stopped-state readback and second main with identical summary. Hosted fixtures are explicitly constructed isolated B3 inputs (CP08 fixture record), not a reacceptance of UK evidence. Production request instead requires the accepted actual UK B3 receipt/proof SHA and original hash-chain. Hosted image is disposable Python3.11.2-slim; only later approved UK execution can prove the existing fixed UK image.

Original111 runtime files, including ledger_service/ledger_prepared/activation_control/p2_sandbox_profile, are byte-identical to B3. Runtime component is copied unchanged from499bcc43, Git blob61ae1b4fc311403ec6fa416464c4e71243b232b8, SHA2563993ab9bd0073a91d8110814e694b2c402ef5b53efb544a3bc44a1debd4231a1.

`production/p2_install/b4_sandbox.py` is the thin adapter. It reads CP03→CP09 and the final B3 receipt, validates interpreter/source/profile binding, invokes the actual original `ledger_service.py --check-isolated-prepared --profile …`, and calls the unchanged original `p2_sandbox_profile.policy()` on a newly constructed isolated two-agent policy. It never uses the recovery controller as the application, calls build/listener, or replaces the application with a generic test service.

Finite readiness is `CP10_READY` → structured `CP10_FINITE_READY` bound to exact request/B3 receipt/config/policy/role. The endpoint is served only after actual original config consumption, original policy validation, cap/no-new-privileges checks and workspace access probes succeed. This is a domain-specific finite adapter endpoint, not canonical-ledger business readiness or an OpenClaw task. Original service start authorization, service_uid UNKNOWN and role handoff NOT_READY stay unchanged; they are not marked PASS.

| Identity | Meaning | Authority |
|---|---|---|
| Owner host UID0 | Existing Docker transport/lock and protected readback | Only fixed new B4 inputs, directories, two finite containers and logs after confirmation |
| B3 preparer UID1002 | Original immutable prepared identity | B3 mounted read-only |
| B4 finite developer UID/GID1002 | Separate bounded process/session/container | Own role directory RW; workspace RW |
| B4 finite platform-engineer UID/GID1002 | Separate bounded process/session/container | Own role directory RW; workspace RO (actual EROFS write rejection) |
| Normal dispatcher/callback/root activation identities | Original B7 startup roles | Unchanged; no substitution with the finite UID |

## Frozen package

[Delivery artifact12244125660](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39377081631/artifacts/12244125660), ZIP SHA256 `c09891fb623e214d6b2a1d18060849713496a1fa1940a1d7cb0b8231b62fbadf`.

[Actual Hosted evidence12243822336](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39377081631/artifacts/12243822336).

| Item | SHA256 |
|---|---|
| wrapper | a58a5abf91d767dee8b23475c86808bbf62e159bb7f45c08697e58b6240bb9c1 |
| bundle | ba8893ba656170b441fe39c4b672905458549172dc0f5aac28a8701f44cf1800 |
| internal tar (239447 bytes,118 regular files) | c8703bc4ed340e08ebaa3647bbc76813d5e9f313910d2984fc6b776d3924a458 |
| fixed request | f3b1c0ace66b4c9602af73c83d596ab23ab7f254a1aac4609cbf2e6d5da53f41 |

The artifact was downloaded and its ZIP digest, portable relative SHA256SUMS, all tar members, source identity and111 unchanged application files were verified. Bundle is available at fixed commit042e909223c333307c6abb2b737b01fd71a67481. [OWNER_COMMAND.sh](OWNER_COMMAND.sh) is the complete one-command candidate, pending Owner confirmation; UK NOT_EXECUTED. Bootstrap has a3.6 grammar check; its network path has not run on UK. The actual wrapper passed exact3.6.8 transport/API and Hosted actual-main tests.

## Complete proposed side effects

1. Existing host root/Python3.6.8, fixed hostname/base0700 and existing `.formal-cli.lock`; no Python upgrade, image pull, user creation or existing chmod/chown. Host downloads exactly pinned wrapper/bundle over HTTPS into new root0700 `/var/lib/xuanjun-p2-isolated-test/b4-sandbox-inputs-20261020`, root0600 input files and unique bootstrap stdout/stderr. Containers have no network.
2. New private logs, root-owned immutable B3 snapshot/summary/intents and118-file staging tree. Only newly created file FDs receive exact permissions; new source files0444/directories0555. The original verified B3 transport91e77a76 is reused, not rewritten.
3. New `/var/lib/xuanjun-p2-isolated-test/b4-sandbox` and its `workspace`, `developer`, `platform-engineer` subdirectories0700/1002:1002. Only newly created directories are chowned; any existing mismatch HOLD. This explicitly adds write access only to these new B4 resources.
4. Two named finite containers: `p2-b4-finite-developer`, `p2-b4-finite-platform-engineer`; UID1002:1002; fixed existing image5341…; `/usr/bin/python3.11` with already accepted binary SHA9bee…; networknone, readonly root, cap-drop ALL, no-new-privileges, pids96, memory512m/swap1g, tmpfs/root128m0700 and/tmp64m1777. Reuse validates image/argv/labels/mounts/isolation and rejects privileged/extra capabilities/devices/shared PID/IPC namespaces.
5. Source/application RO, entire B3 root RO, B4 root RO; overlay only current role directory RW. Developer workspace RW; engineer workspace RO. The other role remains RO. No production DB/Signer/Registry/credentials/Docker Socket is mounted.
6. Each container executes the original runtime CLI against the fixed original consumer adapter; fresh management processes inspect/recover the same completed operation before container exit. Inside, the finite consumer has its own PID/start/session/group identity, domain readiness socket under its own B4 role root, runtime journal/receipts/collector/logs, an8-second readiness-loop deadline after initial validation, and verified stop/recovery. Developer writes one retained `workspace/developer-probe.json`; engineer reads it and proves writes fail EROFS. This is a workspace access probe, not B6 database activity.
7. Per-role CP10 receipt, immutable step-start/inspect/stop/recover records, runtime original commit receipt plus new observation receipts, actual consumer observation/exit, candidate sandbox policy, health socket inode and retained logs/pending hard links. Sockets are left as special-file metadata; not read or copied as ordinary files. All containers/logs remain for inspection; no automatic removal on UK.
8. Host rechecks actual role files/hash references, STOPPED journal, terminal container state, complete unchanged B3 snapshot and absent B3 DB/canonical socket; then writes protected aggregate summary. Exit0 alone is not success.

## Explicit time limits

Original ledger configuration consumer subprocess:5s per invocation. Runtime startup monitor:1s, Unix readiness total:2s, connect/read:.1s each. The finite consumer readiness loop lasts at most8s after its initial B3/config validation; this is not a claim of8s total from process creation. Each management CLI is capped25s by the container roundtrip (internal runtime CLI cap15s); each verified Docker start/wait is capped120s by the reused host transport. Probe or management timeout never means success.

## Failure/recovery rules and coverage

* No start on inspect of an unstarted role. Changed B3 receipt/source/chain/identity or role path is rejected. Normal ledger PREPARATION_PROFILE_CANNOT_START guard remains enforced.
* Bad domain response is HOLD and the verified runtime group is stopped. Wrong RW mount for engineer is rejected. Deadline independently ends the consumer; runtime missing-process recovery stays HOLD and never relaunches it.
* SIGKILL after start: finite process/collector eventually stop; same PID retained; missing completion evidence remains HOLD. No empty reset or retry counter.
* SIGKILL after verified stop: preserved original start/inspect/stop records allow same-operation recovery and publication without new start. New inspect/recover returns the same immutable CP10 receipt.
* Same host command after success verifies exact exited owned containers plus actual current evidence and immutable host snapshot/summary; it does not restart either role or B3. PID values are local to their recorded container namespace. No cross-container PID adoption: outside that namespace the host uses inspected container terminal state and hashed evidence, not a guess based on coincident PID numbers.
* Unknown/partial launch, identity mismatch, changed package, nonzero exited container or conflicting existing output HOLD with original logs/containers/files retained. No cleanup, socket removal, directory reset or new attempt is embedded. Stop/wait may affect only an already verified owned finite container; an outer timeout reports UNKNOWN_RETAINED.

Expected status is **CP10_FINITE_COMMITTED** for this limited new-isolation contract only. Actual UK finite run remains NOT_EXECUTED. Original OpenClaw host profile application/full legacy sandbox equivalence is NOT_CLAIMED. No B5 plugin, B6 DB/WAL, B7 ACTIVE/long-lived service, P3 task/model call or production mutation. Service UID provisioning/normal activation remain later-stage requirements, not new CP10 gates. The old R03 history remains UNKNOWN and is not queried. No Grant/five-attempt allowance was added.
