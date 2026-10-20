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
