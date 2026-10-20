# B3 CP04–09 preparation delivery — pending Owner confirmation

ISOLATED_TEST_ONLY. Source/test commit `1efb406948e407313298ec860f75656235f19f08`, tree `f4b4623798277c85dc42cff1d3c753ddcc8b4af2`.

Hosted CI [39374474409](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39374474409): SUCCESS. Exact Python 3.6.8: 18 tests; Python 3.11 host tests: 18; real disposable Docker recovery chain: 1. The real `main()` test replaces only host identity/Docker boundary; the separate Docker test performs real UID1002/65534 execution under umask077. These are Hosted results, not UK execution evidence. Journal CI 39374474391: SUCCESS.

## Two corrected host gaps

* `publish`: only the new O_EXCL inode receives fchmod; mode and bytes are read back before/after non-overwriting hard-link publication. Existing objects with conflicting mode/content HOLD, never chmod. Root-private parent directories remain unchanged.
* `prior_snapshot`: records ten original regular files plus activation/data/run directory metadata separately. Verifies original pending/final hard-link pairs, fixed activation children, empty reserved data/run directories; unknown objects, links, unexpected DB/socket or source mutations HOLD. Never reads directory contents as ordinary file bytes. Prepared output is the sole excluded mutable subtree and must retain its expected owner/mode.
* Read stability excludes access-time changes caused by reading, while preserving device/inode/owner/mode/link-count/size/mtime/ctime checks.

## Fixed package

[Hosted artifact 12243350205](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39374474409/artifacts/12243350205), ZIP SHA256 `305241fc9a029d5056b54054237f4091d532a903654021ff07615bde53b1ac11`.

| Object | SHA256 |
|---|---|
| p2-b3-final-bundle.json | ba7216b1b9e2f18c9ac13b6f79ca52f8b50259b9033e40053bb1b58681144d1e |
| p2_b3_owner_finalize_20261020.py | b597a4b662df58709e1c5fd91e7367c6b52f34721b2276eedd3ca6e12d99216a |
| internal tar (233242 bytes, 118 files) | c7e2fcca6f9d4a26a080f2a6ef587fc7f4659ccce8feba3f8714ed32e917074d |

Artifact ZIP digest, portable relative SHA256SUMS, all tar entries and wrapper identity were independently read back. The identical bundle is frozen at commit `e5399515d3f05ed13ae6affe07ff651818951118` in this directory. Existing real application files, B1/B2/CP03 and request identity are reused.

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
