# B5 / CP11 — PARTIAL: original source package ready, real loader unavailable here

Task PR17 #6284722235; baselineee183c19. Inherit actual B4 accepted receipt from the same comment: developer a020db165096f649d62aa67c8a108ef4607416cc50998dcd6725d91b96c2ca56, platform-engineer2288bcab7e5db568c5a70c979b85cde3218b9b3da194207556577e48c9129c65. B1–B4 are not reinstalled.

## Verified source conditions

The original plugin11 files remain unchanged. The source-only preparer builds a deterministic versioned archive with every file SHA/mode; it rejects bad hashes, links/unknown members and conflicting partial outputs without overwriting a prior version. This is an offline source-package builder, not a new plugin installer. Same-output preparation is idempotent, but **is not OpenClaw install/recover acceptance**.

Original package declares plugin0.1.0 and extension `./plugin.mjs`. Manifest requires exact bindingFile/bindingSha256. Original plugin.mjs first checks the root-protected binding, constructs original host bindings, then registers native execution/Owner handlers and before_tool_call. All protections remain.

Historical project metadata points to Node24.21.0 at `/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node` and OpenClaw2026.9.9 under that Node installation. Exact current Node binary SHA is UNKNOWN. Existing Python sandbox evidence proves Python, **not Node/OpenClaw availability inside that image**. Local development Node24.19.0 is recorded only as local; not the UK runtime.

Pinned official source-profile package.json SHA214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95 declares engines `>=24.16.0 <25 || >=26.1.0`,66 direct dependencies; SDK runtime exports include `./plugin-sdk/core` and `./plugin-sdk/runtime`. Full installed transitive closure is not supplied in the current delivery. Npm tar SHAa46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7 is a historical source pin, not proof of an existing usable isolated SDK mount.

Historical UK metadata, explicitly READONLY_METADATA_NOT_RUNTIME_ACCEPTANCE, records compiled loader `dist/loader-runtime-load-DpgEqnzx.mjs` SHA3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787 and context `dist/context-DyPstb2Q.mjs` SHAdb7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320.

Primary upstream source was read at commitbcfc88812a35243893585dbeca87ca41b48272ca:
- [real loader facade](https://github.com/openclaw/openclaw/blob/bcfc88812a35243893585dbeca87ca41b48272ca/src/plugins/loader.ts): loadPluginRegistryHandle calls the real loader with activate:false.
- [loader options](https://github.com/openclaw/openclaw/blob/bcfc88812a35243893585dbeca87ca41b48272ca/src/plugins/loader-types.ts): full/validate/cli-metadata, runtimeSideEffects and expectedSourceDigests are distinct; metadata/validation alone is not runtime registration.
- The exact callable export in the historical compiled loader is UNKNOWN; do not guess its minified alias or substitute a local createPluginRuntime/mock API.

## Actual capability gaps (concentrated)

1. No complete compiled OpenClaw loader/SDK dependency tree exists in this workspace or delivery. The31-file official source-profile fixture covers startup source and package metadata, not a usable real plugin loader. No real loader was executed. Need the **existing** UK Node/OpenClaw tree's approved read-only source/identity/mount reference and exact compiled export. This does not imply upgrading/installing Node or pulling an image.
2. Original positive methods do not provide the required no-effect function: `preflight` calls canonical store preflight and checks OAuth/config/engine; `inspect` calls ledger read and may CAS terminal state/stop a unit; `report` writes CAS; `stop` cancels/stops; owner delivery is an effect. admit/launch/model/real-ledger writes are forbidden this round. No existing safe positive authenticated plugin function has been demonstrated. A new helper/unauthorized response/no-op hook is not substituted. The original acceptance owner must identify the permitted existing no-effect function or separately scope a minimal read-only plugin capability; current code does not invent it.
3. Actual authenticated Gateway invocation/role rejection, real loader bad-plugin rejection and loader-owned lost-response/restart recovery remain NOT_EXECUTED. Direct Node guard tests are only component negatives and cannot satisfy these items.

These are B5 dependencies/capability gaps, not a request to reconnect old Writer/Grant/history or move B6/B7 earlier. Missing OAuth/ledger from an old preflight is not turned into a new admission condition for the rewritten isolated path.

## Source-only checks and exact current operation

`python -B production/p2_install/b5_inputs.py report` emits the honest unavailable-capability report; `prepare --output <private-local-output>` creates only an offline source tar/manifest/report. These commands do not load/install a plugin. Hosted uses existing runner Node for8 original guard negatives; no mock registration, Gateway or SDK runtime is fabricated. Python tests cover exact archive/modes, digest/link/unknown-member rejection, same-output readback, partial-state preservation and previous-version protection.

**B5 installation command: NOT_READY / NOT_EXECUTED.** No placeholder installation command is delivered as executable. Producing a real complete command before the above runtime/export/function binding is known would be guesswork.

## Complete proposed future action boundary, not approved or executed

After the gaps are closed and the final command is separately frozen: only a new versioned B5 plugin root/state root and readonly source/SDK mounts; inherit B3/B4 read-only. Keep SDK path/owner checks (home/.openclaw UID1002, permitted root/1002 protected ancestors, nlink1 SDK files) and root-owned protected binding. Mounting only a tools subtree under root-created home directories would fail the original SDK_HOME_IDENTITY guard; do not waive it or mount a real home containing credentials. Any new isolated home/mount layout must be listed and approved together.

A real loader run must use a caller-owned non-activating registry, record loaded plugin ID/source digest/actual registrations, and an approved bounded no-effect function via genuine host authority. Missing modules/export/binding/role/auth must HOLD. Preserve per-version load intent/observations/receipts and source bytes; after response loss inspect/recover the same loader-owned instance/version, never clear directories or blindly load another instance. No changes to existing Gateway/config/permissions, no runtime installation/image pull, no credentials/auth profile fabrication, no admit/launch/model/Owner delivery/real ledger mutation. Exact process/mount/time limit/receipt paths remain UNKNOWN until real loader wiring is bound; no estimated count or invented PASS.

Current result: **SOURCE_PACKAGE_PREPARED; CP11 NOT_EXECUTED; real registration/function/recovery UNAVAILABLE**. UK unchanged, model_calls0. Independent source work is saved; only dependent loader/functional operations remain blocked.


## Frozen source checks (actual results)

Source/test commit10f8f91ad260a8b954b0704a93229d1847340933, Tree2699c741f43258a0059b14019722dcfb5f079f29. Hosted [39380788469](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39380788469): SUCCESS for **source/guard scope only**. Python3.11/3.12 each9 tests;8 original Node guard negatives. Actual runner Nodev22.23.3 does not satisfy the OpenClaw2026.9.9 engine range; it was used only for original component guard tests, never for SDK loading. No new Node/OpenClaw runtime was installed and no image was pulled.

Both Python artifacts were downloaded and verified; their internal three files are byte-identical. Original plugin package `p2-native-controller-0.1.0-3dd9f8c4b8b0d4ff.tar.gz`,14696 bytes,11 unchanged source files, SHA25683eac1fca2bf811e8e0ee276cd40f577dc1d0fe77bd425499420fe9f58a9cd8b.

- [Python3.11 inputs12245606524](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39380788469/artifacts/12245606524), ZIP SHA8bbd8242169ad4ff57103963391adba82ca5395d8c9ef30e605f587141f90601.
- [Python3.12 inputs12245402436](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39380788469/artifacts/12245402436), ZIP SHA8e054450aeab07a7b829517fe298b7ae4cf073deb71bf97d91d12b4a3e1bd1c6.

Manifest and honest capability report are committed alongside this status. CI success is not CP11 success.

## Minimal dependency read candidate, not installation

[SDK_READ_ONLY_CANDIDATE.sh](SDK_READ_ONLY_CANDIDATE.sh) is one complete **not-executed** metadata command for separate confirmation. It downloads the pinned Python script into memory, drops to existing xuanjun_dev/UID1002 and reads only the fixed Node binary plus package/loader/context files. It records SHA/owner/mode/size and static export-name hints. No files or directories are created, no runtime/plugin is imported or executed, no Gateway/DB/auth/config is read or changed; reads may change atime. Exact transitive closure and actual Node execution version remain UNKNOWN/NOT_EXECUTED. The static export-name hints are not runtime export verification or authority to load a module. Exit0 means only that metadata reporting completed, not readiness.

Inventory script SHA23fc5facba74ef4db05b0c982c73f36b0c8a498a43e71fc86e5282e5ac336dce; Python3.6 grammar checked, exact UK3.6.8 execution NOT_EXECUTED. No old environment/RAM/Writer/Grant scan is included. This candidate closes only the smallest missing measurements; it cannot solve the absent permitted positive functional entry. Original loader/registration/auth/function/recovery operations remain blocked and are not replaced with the metadata command.
