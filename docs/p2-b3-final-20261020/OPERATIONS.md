# B3 CP04–09 preparation delivery — pending Owner confirmation

ISOLATED_TEST_ONLY. Source/test commit `701113c7c453ef16cfa39b72dcd0f8c80b088f0b`, tree `358ece80b0baf95e797909523c6fce0aa4d56c86`.

Hosted CI [39374783185](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39374783185): SUCCESS. Exact Python 3.6.8: 19 tests; Python 3.11 host tests: 19; real disposable Docker recovery chain: 1. The real `main()` test replaces only host identity/Docker boundary; the separate Docker test performs real UID1002/65534 execution under umask077. These are Hosted results, not UK execution evidence. Journal CI 39374783198: SUCCESS.

## Two corrected host gaps

* `publish`: only the new O_EXCL inode receives fchmod; mode and bytes are read back before/after non-overwriting hard-link publication. Existing objects with conflicting mode/content HOLD, never chmod. Root-private parent directories remain unchanged.
* `prior_snapshot`: records ten original regular files plus activation/data/run directory metadata separately. Verifies original pending/final hard-link pairs, fixed activation children, empty reserved data/run directories; unknown objects, links, unexpected DB/socket or source mutations HOLD. Never reads directory contents as ordinary file bytes. Prepared output is the sole excluded mutable subtree and must retain its expected owner/mode.
* Read stability excludes access-time changes caused by reading, while preserving device/inode/owner/mode/link-count/size/mtime/ctime checks.

* Container adoption rejects Privileged, extra CapAdd/devices and shared PID/IPC/UTS/user namespaces; eight mutation cases are covered. Intermediate bundles are superseded; only the hashes below are frozen.

## Fixed package

[Hosted artifact 12243061546](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39374783185/artifacts/12243061546), ZIP SHA256 `4d8542ebb58f65af8577c422e9b3f50cf49bf508aad32e92a60bdc4fea30448a`.

| Object | SHA256 |
|---|---|
| p2-b3-final-bundle.json | acc3befbf0031cdee8bedbf87524c1840d44e8682ba9418f21949963f39c28d5 |
| p2_b3_owner_finalize_20261020.py | 91e77a767752f3714cd670e41ae6eebf6c834707b016b59a9fbe81cab344b753 |
| internal tar (233377 bytes, 118 files) | 654db8c34c65c83e87e169c35c1c54da4c48c31d8243badc3a85cbfce4e1ba8f |

Artifact ZIP digest, portable relative SHA256SUMS, all tar entries and wrapper identity were independently read back. The identical bundle is frozen at commit `5d8eeac0d39e9eb513c3bb0df8abc69fdf074c78` in this directory. Existing real application files, B1/B2/CP03 and request identity are reused.

## Exact proposed operation

[OWNER_COMMAND.sh](OWNER_COMMAND.sh) is the single proposed command; **UK NOT_EXECUTED**. Bootstrap syntax checked against Python3.6 grammar; its network/download path has not run on UK. The actual wrapper and host APIs passed exact Python3.6.8 Hosted testing.

After Owner confirms this complete action list:

1. Host root reads existing formal lock, verifies fixed host/base protection; creates only `/var/lib/xuanjun-p2-isolated-test/b3-ledger-final-20261020` (root0700), two pinned root0600 downloads, unique bootstrap stdout/stderr. HTTPS downloads run on host; containers have no network. No image pull.
2. Wrapper holds the existing lock; creates private logs, source snapshot, staged 118-file source tree, immutable intents/proof/summary and retained `.pending-*` hard links. Only new source directories become0555 and new public source/proof files0444 via their creation FD. It does not repair existing permissions.
3. Creates four fixed UID1002 worker containers (execute, recover, inspect, recover) and one independent UID65534 observer. Read-only root, no network, cap-drop ALL, no-new-privileges, pids96, memory512m/swap1g; fixed tmpfs limits. Uses existing fixed image and `/usr/bin/python3.11`; no Docker Socket, production data, Signer or credentials mounted.
4. Workers mount B3 root for prepared output and overlay original activation/config/receipt read-only. Stage source/application is read-only. Observer mounts only prepared target and pinned probe read-only. Owner root captures actual Docker identity and observation; UID1002 receives only the fixed root-owned read-only proof file.
5. First execute saves CP04–07 and retains CP08 HOLD for missing observation. Independent denial evidence is collected; same-request recover commits CP08–09. Fresh inspect/recover processes must return the same immutable preparation receipt. Host verifies real terminal files/hash-chain and unchanged original source snapshot; exit0 alone is insufficient.

## Checkpoints and recovery

All containers/logs/pending state remain. Same command resumes by validating exact staged bytes, original snapshot, container identity and pinned intents; it does not remove exited containers or reset checkpoints. Unmatched identity/mode/content or uncertain partial work HOLD. A timeout preserves UNKNOWN and logs; reconcile retained state before retry. Unknown objects and extra pending links are not silently discarded. No cleanup/reinstall command is included.

Expected terminal status is **PREPARATION_COMMITTED**, `full_b3_complete=false`, `service_started=false`, `production_permission=false`. Real ledger config consumption is proven through its non-start preparation profile. No business process/DB/socket is started, no activation transition is performed, and this is not full B3 or production installation success. Original R03 history remains UNKNOWN; no Grant/five-attempt admission is introduced.
