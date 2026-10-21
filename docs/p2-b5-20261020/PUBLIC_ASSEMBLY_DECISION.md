# B5 public assembly decision after manifest join

Continues ad2c6d1d / PR17#6314150322. No SDK/parser/server/installation execution. Prior10native-drain and earlier accepted evidence reused, not rerun.

## Material and reference checks

Owner attachment manifest-join.redacted(1).json162364 bytes / SHA2568757c44ba0321f2b8873390a8aca6bb954cb319d0cf2920b47753f16585568ae matches. All384 member names,parent,line,route match canonical inventory individually. Unique matches384, no absent/ambiguous, total3842258 bytes; inspection163/1597587 B,public_ws288/3039504 B. Route totals overlap. These known size/SHA rows supersede previous metadata UNKNOWN; no original-manifest request is needed.

One actual discrepancy is retained: join.source_inventory_sha256 says aa601bc0632c08f693d63d5b1ef02ff08de1baf5b20706684c61c020c6cf0c57. Canonical ad2c6d1d inventory is82903 B, SHA25663345c45bd7d5af61f93ded86543978465ed52f38765359ed78296031c62fb4e, Git blob9f858ce882fd89b0b645425f4c136b0fc97a476a; local bytes match that Git tree blob. Do not silently rewrite the uploaded attachment or report whole source-reference PASS. Row semantics pass independently; source-reference stays HOLD pending Dots correction of this reference only. No UK action or recapture is required to correct it. Enriched evidence/manifest-bound-prerequisites.json preserves both hashes and all384 known rows. Empty selected_members remains empty; no new file is approved by this join.

## Supported public ownership shape

| Owner | Actual source-backed interface | Lifecycle obligation |
|---|---|---|
| Inspection registry | loader-runtime-load-DpgEqnzx.mjs L6168 acquirePluginRegistryForInspection exported as t; forces activate:false/cache:false; owns fresh registry/resources | Validate real inspection registry, then await original lease.release and journal RELEASED. This is independent of a running Gateway registry. |
| Dedicated isolated Gateway | server-ChnNHwLm startGatewayServer → server-start-Bz-KV48j startGatewayServerCore → createGatewayKernel; pluginRegistryOwner created from native bootstrap.pluginRegistry | Kernel privately owns connectionWork,live registry,context. Do not demand a public reference to internal kernel or supply inspection registry as an active runtime. |
| Authenticated client | already received client-B4O1WKhF.mjs77353 B/SHA5434ab96d41c82f8717e0bb5b1046f06d41cac0b3da9a5cbf384e0aaad8cf5cc exports GatewayClient as t | Use original connection/handshake/authority and client cleanup. Constructor/response fixture is not authentication. No hostDeps override/fabricated client/scopes may establish acceptance. |
| Native request scope | server-methods-DJEQKCcV L667 chooses methodRegistry.pluginRegistry before native request scope/active registry; original WS context supplies client/authority | Actual runtime registry must be loaded and bound by original Gateway. Metadata source/declaration digest establishes expected plugin bytes, but alone is not proof of runtime registry identity/custody. |
| Public server close | original public handle.close → beginClosePrelude/prepareClose → runGatewayCloseSteps → native required sidecar/connectionWork/late-cleanup joins | Await successful full native close; no artificial owner drain, copied class, monkeypatch export or active-registry setter. Failure remains HOLD with original handles/state preserved. |

This proves a **public-handle lifecycle shape**, not an executable safe configuration or completed native wiring. The existing withPublicWsContract/internal-owner-injection path stays CONTRACT_ONLY and is not promoted to an installation route. New b5_public_gateway_lifecycle.mjs expresses sequential ownership: complete/release inspection first, then separately acquire the public Gateway handle, run an externally still-unbound original authenticated client, always await native close. Registry objects are never merged or claimed equal. It returns PUBLIC_LIFECYCLE_CONTRACT_ONLY/runtimeBinding UNBOUND/authenticatedDispatch NOT_EXECUTED. It does not import or start SDK itself.

The helper is intentionally not the final installer: startGateway and runAuthenticatedClient are unbound composition callbacks. It does not grant startup permission or persist a false live-runtime success receipt. Uncertain startup without a returned handle cannot be cleaned up by guessed handles, and requires original startup rollback evidence; the helper propagates the failure and does not retry.

## Real remaining blockers, consolidated

| Blocker | Exact known callsite / material status | What can close it |
|---|---|---|
| Native startup plugin ownership/profile | Received coreL5202 dynamically imports dist/server-startup-plugins-Cajv-q3y.mjs;L5383/L5394 calls prepareGatewayPluginBootstrap;L8243 calls loadGatewayStartupPluginRuntime. That module is not received and was excluded from the384 eager-only boundary join. | Its exact original-manifest row and real bytes must demonstrate discovery/load options,original live registry claim,restricted readonly plugin configuration and lifecycle. A guessed injection is prohibited. This is a new genuinely distinct metadata row, not re-request of known384. |
| Native startup config/auth/side-effect policy | Received coreL5201 dynamically imports dist/server-startup-config-Hx2M1x7s.mjs, then loadGatewayStartupConfigSnapshot/applyGatewayAuthOverridesForStartupPreflight. Not received; not included in384 static boundary list. | Read its actual policy to establish isolated config/auth/defaults and startup effects. The public root may prepare DB/model catalogs/worker services; merely choosing loopback or updateCanary/test-mode is not proof of the approved B5 restrictions. |
| Public client eager dependencies | client-B4O1WKhF is already received. Adding it as a root adds exact static boundaries dist/proxy-lifecycle-Dl57fEmL.mjs and dist/url-protocol-OU3K-ySz.mjs beyond the original384. | Reuse Dots original manifest to bind these2 additional rows in the same metadata response as startup2. Not a new full manifest request or4 separate onsite trips. Static imports remain required at module import even if SSH tunneling is disabled; no execution is done to inspect them. |
| Source dependency closure |384 rows now have size/SHA; actual bytes not received. Public route plus client has386 eager boundaries before unseen dynamic/resource/package resolution. | Only after startup/profile route is justified can the necessary subset and downstream transitive/package/resource sets be frozen.386/384 must not be selected by count/size alone. No dependency is declared optional merely because method describe is read-only. |
| Package/native/image |33 bare specifiers/14 packages; known Node126595440 B/SHA7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c; ELF interpreter/library names known, actual runtime/image compatibility unknown | Resolve exact package entries/exports/conditions and native/resource needs from real material. Existing Python image cannot prove Node compatibility; no Node126MB inside original16MiB member candidate, no hidden limit increase. |
| Real authorization and recovery | Original client class/WS/auth code known; no real configured handshake,current authority,live-registry provenance or native startup/stop evidence | Separate approved isolated execution with original authenticated metadata positive/refusal,disconnection,original client stop/full server close,failed startup cleanup and restart/no replay. No credential values,manual scopes or fixture authentication. |
| Source evidence reference |384 rows semantically match; join source SHA reference differs | Dots correct that single reference or provide exact original serialization underlying the claimed SHA. Do not overwrite attachment to make it pass. Independent source work continues. |

The four newly named dependency rows form one **metadata/assembly-analysis frontier**, not a frozen installation or extraction batch. Their byte/SHA fields remain UNKNOWN until the existing manifest is joined; requesting original known384 metadata again is unnecessary. They are named from exact callsites and original client's real static import graph. Unread startup code may expose additional required effects/dependencies, so this is not promised as the last collection.

## Decision and next action

`selected_members=[]`, `INSTALLATION_BATCH=HOLD_ASSEMBLY_PROFILE_AND_CLOSURE`. No final required installation batch can honestly be emitted now. Public lifetime ownership can use independent inspection and original server handles, removing the need to forge an exposed kernel; **native bootstrap profile,real registry/authority and runtime dependency closure remain unproven**.

Next no-server action: Dots one response for correction plus the4 new existing-manifest rows; Work uses those real assembly inputs to decide the supported restricted public startup/profile and one exact combined missing-material batch under original resource ceilings. Any new onsite command requires its own final concrete confirmation. No individual-file onsite command is issued by this delivery. B1–B4 unchanged; SDK/real authentication/installation NOT_EXECUTED.

## Actual checks

New5 lifecycle fixture cases cover inspection-release-before-start,inspection release failure preventing startup,auth error still closing,close error HOLD and nonpromise close refusal. Existing registry validation is used; SDK/authentication not mocked as a success claim. Local tests PASS. Hosted run is recorded in PR17. Metadata audit verifies attachment SHA,384 unique semantic matches/route sums and canonical Git blob; the source SHA discrepancy is a real FAIL/HOLD, not turned into a green test. Existing successful tests are inherited only.


## Current consolidated decision — PR17 #6316275680 (supersedes small extraction next steps)

The three-member candidate at8bd6da25 is an INTERMEDIATE ANALYSIS batch, not a final installation batch. Its field execution is PAUSED/NOT_EXECUTED in this window; no corresponding execution receipt has been received. Earlier confirmation attempts are not authority for this action. If Owner already executed it, preserve that output and incorporate it; never rerun. No new extraction candidate or onsite command is part of this revision.

### Frozen route and intended profile

Route choice is fixed: real inspection lease for the readonly plugin → await original lease release → dedicated original public startGatewayServer → await original startupSettled → original GatewayClient authenticated xuanjun.capabilities.describe → original client stop → original public server.close and native drain. Inspection and active registries remain separate owners. No internal kernel injection, copied dispatcher, manually fabricated client/scopes, mock Gateway or test-mode promotion.

Profile intent is fixed, but its executable config is DRAFT: existing isolation envelope, nonroot UID1002, no external network, read-only SDK/code and container root, cap-drop ALL/no-new-privileges, no production data/credentials/Docker socket; independent ephemeral HOME/config/state/run roots only. Loopback communication is within the same isolated namespace. Only the readonly plugin is intended; no model request, ledger business operation, OAuth, admit/launch or production effects. An original authentication chain must use an isolated identity and actual native checks; no real credentials or identity are created by this document. Existing compatible Node24.21.0 is the intended runtime, subject to actual image/ELF binding below. Original updateCanary is a candidate native restriction, not proven sufficient and not forced into a fake test environment. Exact startup flags/config and all native startup writes/processes cannot yet be frozen truthfully because their actual controlling implementations are unread.

### Complete currently known boundary, derived from this route

Recomputed from loader-runtime-load-DpgEqnzx.mjs, server-ChnNHwLm.mjs and client-B4O1WKhF.mjs, plus7 exact-witness native dynamic analysis roots in consolidated-runtime-boundary.json. Not a blanket copy of the prior384/389 list. Every received-source edge records importing parent/line; each available source has byte/SHA. No SDK/parser/resolver execution.

| Category | Exact result | Persisted full evidence |
|---|---:|---|
| Available reachable source bytes |788|consolidated-available.json: names/bytes/SHA; not all bodies manually reviewed|
| Known necessary missing boundary with manifest binding |360 /3750367 B|consolidated-known-missing.json: every path, parent/line, bytes, SHA, reason and binding source|
| Missing boundary without delivered binding |12 /total UNKNOWN|consolidated-unknown-missing.json: every exact parent/line; unknown fields retained|
| Original384 rows not reached by chosen roots |29|decision record lists every excluded path/reason; not selected|
| Bare specifiers |33 /14 package identities|decision record lists every specifier/witness; exports/conditions unresolved|
| Dynamic call sites in reached readable bodies |194|consolidated-dynamic-sites.json: locations, NOT a selection of194 imports|
| Unsupported one-line static declarations |0|limited scanner scope only; not a complete JS parser proof|

These360 items are known mandatory **boundaries** for this selected route, not a claim that their unread children are already included. Sum3750367 B is a known lower bound;12 unknown files, recursive unread imports, chosen dynamic/package/resource edges are additional. The full file lists are authoritative; this prose does not omit their entries for a smaller claimed batch. No existing788 source is to be recollected. Explicitly read root/core/shutdown/WS/client/loader/native plugin/config/helper/startup-auth/server-plugins source conclusions are in prior pinned analysis evidence; other present bytes are AVAILABLE_BODY_REVIEW_UNKNOWN, not falsely marked read.

### Exact currently unbound source boundaries

| Member | Actual parent | Line | Size/SHA |
|---|---|---:|---|
|dist/background-work-DsUCV0EB.mjs|dist/server-plugins-CzOpf53P.mjs|26|UNKNOWN|
|dist/configured-binding-registry-CSyIGq6m.mjs|dist/server-startup-plugins-Cajv-q3y.mjs|19|UNKNOWN|
|dist/loader-DpAS3szV.mjs|dist/server-plugins-CzOpf53P.mjs|20|UNKNOWN|
|dist/model-allowlist-CxWrlShg.mjs|dist/server-plugins-CzOpf53P.mjs|25|UNKNOWN|
|dist/plugin-lookup-table-S8Uoyk0R.mjs|dist/server-startup-plugins-Cajv-q3y.mjs|21|UNKNOWN|
|dist/provider-integrations-Ud7jCKSS.mjs|dist/resolve-DfWA04S1.mjs|19|UNKNOWN|
|dist/run-with-concurrency-Dtu208ef.mjs|dist/resolve-DfWA04S1.mjs|16|UNKNOWN|
|dist/runtime-fast-path-GHoXsR84.mjs|dist/server-startup-config-Hx2M1x7s.mjs|10|UNKNOWN|
|dist/server-in-process-dispatch-DnQz0IUf.mjs|dist/server-plugin-in-process-dispatch-CBGxjSoo.mjs|12|UNKNOWN|
|dist/server-plugins-node-runtime-BFi-8eds.mjs|dist/server-plugins-CzOpf53P.mjs|27|UNKNOWN|
|dist/subagent-completion-tool-handoff-CMCdoTFy.mjs|dist/server-plugin-in-process-dispatch-CBGxjSoo.mjs|13|UNKNOWN|
|dist/subagent-registry-BXsmuHxo.mjs|dist/server-startup-plugins-Cajv-q3y.mjs|20|UNKNOWN|

### Runtime and unresolved behavior that prevent a complete one-shot promise

- Native config-helper U6x137 B, early4816 B, post-attach53969 B are among the known bound360, not separate new batches. Their exact rows already exist; no manifest re-request. U6x is not presumed equivalent to the received same-name d2n helper. Actual early/post-attach determine plugin loading/startupSettled and effects; until read, executable restricted profile remains unproven.
- Selected unread source bodies can expose additional mandatory imports.194 dynamic locations are not automatically selected; branch applicability must be established from original config semantics. Computed imports/resources cannot be called closed by literal scanning.
- Bare package exports/imports/conditions, package versions/entry bytes, native addons and resource files remain unresolved. Root package dependencies or filename lists are insufficient.
- Existing Node path /home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node is126595440 B, SHA7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c. Its7 ELF library names and /lib64/ld-linux-x86-64.so.2 are known; concrete library bytes/SHA and existing isolation image compatibility are UNKNOWN. This Node cannot fit original16MiB selected-source limit. Do not silently copy it or raise limits. A proven already-present compatible runtime binding or separately agreed runtime provisioning approach is required before any complete installation candidate.
- Prior fixed image sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d proves Python/UID only, not Node/ABI. Actual authenticated subject/current authority, native runtime registry, readiness and full cleanup/restart still need specifically approved execution later.

### One bounded convergence/extraction plan, no command issued

1. Reuse the fixed original retained tar/manifest and all already received material. Join all12 currently unbound rows against that already-held manifest in one offline metadata response; do not ask Owner for the original manifest or separate file commands. Preserve unknowns and ambiguity.
2. Before a new field extraction, settle the whole selected profile/closure in one bounded planning pass: start the exact roots above; reuse present bodies; read required missing bodies as inert archive data in the original protected reader, follow only proven eager/selected dynamic/package/resource edges, and track seen members. Any unproven branch/export/native dependency stays an explicit unresolved item, never default all389. This step describes required convergence behavior; no new tool or field action is authorized or emitted here.
3. A final selection must list ALL required missing files once (path/size/SHA/parent/reason), runtime/image binding and all side effects, excluding every existing file. Check≤2000 selected files,≤16MiB source,≤2MiB single source,≤18MiB tar,≤2MiB report, and unchanged original host/identity/CPU/memory/time limits. If unresolved or over bound, reject before publication of a claimed complete batch; provide the single consolidated failure report rather than another small candidate or enlarged limits.
4. Only when that whole plan is actually bound can one concrete extraction be offered for specific confirmation. Exclusive output/partial receipts retained; existing directory/failure HOLD, no overwrite/delete/rename/blind replay. One successful extraction still means materials only; real SDK authentication/loading/close recovery are a later explicitly scoped validation, not inferred from file transfer.

At present a complete once-only extraction cannot be guaranteed from the received subset. Its precise blockers are12 unknown bindings, unseen recursive/conditional/package/resource implementations, and unproven runtime/image ABI under the existing limits. Merely renaming3 files or selecting360/389 does not close them. This revision freezes route/containment/selection criteria and all known rows; executable profile/complete extraction remains DRAFT, no server action and no installation ETA invented.

### Actual validation and retained checkpoints

New offline enumeration: roots/witness lines matched actual source SHA; unique names checked; all overlapping metadata bindings agree;360 bound-row sum3750367 B;12 unknowns retained;788 available hashes recorded;29 prior rows excluded by reachability; no SDK execution. Old10 lifecycle and candidate Hosted success reused, not rerun. This is documentation/evidence only, no new runtime-code test or CI-pass claim. B1–B4 unchanged. All original archives, failed outputs and previous evidence retained. Final install selected_members remains empty; SDK/authentication/CP11/installation NOT_EXECUTED.
