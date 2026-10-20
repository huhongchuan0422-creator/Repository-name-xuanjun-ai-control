# B5 received-material dispatch registry increment

Task PR17#6293776699; baseline937f4f6a. Source/contract increment only: no archive Node/SDK/parser execution, no server action. B1–B4 and unchanged lease/journal/plugin/host-tool evidence are inherited. The old lease module is byte-identical to937f4f6a; this adapter captures its acquired lease through the existing acquire callback instead of changing the passed component.

## Actual local receipt and source bindings

At23:45 Beijing2026-10-20, normal local attachments materials(1).zip/report(1).json/child-receipt(1).json became readable. Prior Library403 transfer was stopped; no access workaround. Original attachments unchanged. Tar18124800 bytes/SHA25628c4fdee0412242152d93a98e6e44bccfc3bf01e8cfba8f87406a1e8646ca331; all1718 unique regular safe-path members match the exact report set/bytes/content SHA. Report563611 bytes/SHA50ff8d95ec5ddc2ff3d4b19c6b2b509ed156aae9a7ed35e397a915e9a1b8f975; child357 bytes/SHA6843164693365cc38b6f50c8b1f9e3bf4e2689e0aa7a570d827541ba637f62c0.

`evidence/p2-b5-dispatch-20261020/dispatch-static-analysis.json` records actual bindings and concentrated gaps; compressed relative-edge inventory is reproducible source-analysis evidence, not a runtime tree. `dispatch-byte-fixture.json.gz` retains7 exact received public SDK source buffers (including package/descriptor) for static tests, with upstream MIT license. This is not repackaging or installing the SDK.

| Actual file | Verified static seam |
|---|---|
| registry-CAoo0u-p.mjs | createGatewayMethodRegistry=n; createPluginGatewayMethodDescriptors=r; caller must not guess alternate exports |
| descriptor-C-QJ0nle.mjs | createPluginGatewayMethodDescriptor=r, plugin owner, normalized scope, profileAccess default required |
| loader-runtime-load-DpgEqnzx.mjs (inherited fixed pin) | registerGatewayMethod stores the real handler and SDK-created descriptor in the same inspection registry |
| authenticated-request-dispatch.server-methods.runtime.js | Reexports fixed runtime-C6C-oLg5.mjs |
| runtime-C6C-oLg5.mjs | Imports server-methods-DJEQKCcV.mjs#r as handleGatewayRequest and reexports canonical name |
| server-methods-DJEQKCcV.mjs | Owns handleGatewayRequest=r; prefers opts.methodRegistry if it owns requested method; retains native authorization/request scopes |

The runtime bridge is only the callee boundary. It is NOT the full authenticated WebSocket dispatcher or a handshake. No module containing createGatewayAuthenticatedRequestDispatcher was found in the1718 received members. Full dispatcher/composition-root compiled bindings remain UNBOUND; the compiled module is not invented from the runtime bridge.

## Adapter and trusted ownership

`b5_dispatch_registry_contract.mjs` binds the exact7 source buffers and fixed n/r namespace properties without importing/evaluating SDK code. A namespace supplied by a caller or test is not proof that it was imported from the same immutable dependency closure. The trusted real composition root must supply that provenance later. No arbitrary aliases, dynamic module paths or JSON VERIFIED flags provide trust.

The live method-registry adapter:
1. Reuses readonly lease registry validation; asks real SDK createPluginGatewayMethodDescriptors for its descriptors. Requires exactly the metadata method, same handler identity, same plugin owner/id, admin method policy and profileAccess required. No invented handler-only fallback with unknown owner.
2. Uses real createGatewayMethodRegistry(descriptors, lease.registry). Requires pluginRegistry to remain the exact acquired object, handler identity unchanged, one method and native profile/scope metadata intact.
3. Changes only handler.getMethodRegistry in the existing real WebSocket composition parameters. That original dispatcher then supplies opts.methodRegistry before bindWebSocketRequestMutationAuthority. It does NOT clone already authority-bound GatewayRequestOptions, set a global active registry, substitute extraHandlers, or call handleGatewayRequest directly.
4. Only describe frames can reach the native dispatcher. Client/auth/scope claims in request frames or composition configuration are rejected. Existing authenticated-owner arguments are forwarded unchanged; no client.connect/scopes/profile/authPolicy is constructed or changed.
5. The native dispatcher retains handshake policy/device revocation/session generation/current-client authority, response publication and request lifetime. Native handleGatewayRequest keeps authorizeGatewayRequestPreDispatch, authorizeGatewayMethod, authorizeAuthenticatedProfileForMethod, withPluginRuntimeRegistryScope and withPluginRuntimeGatewayRequestScope. This adapter adds no synthetic authorization layer.

Identity/grant trust comes ONLY from original authenticated transport and its live owner/policy objects. Plugin method scope is required method policy, not a grant to a caller. The adapter's structural checks cannot authenticate a fabricated composition root; this is a trusted-root internal contract, not a public request endpoint or authentication boundary. Fixtures deliberately have no client scopes and never establish real authentication.

Actual received native code explains why the outer owner is indispensable: authorizeGatewayMethod has a pre-connect compatibility path; authorizeAuthenticatedProfileForMethod does not itself manufacture/require a handshake for every compatibility caller; readGatewayRequestMutationAuthority can construct native-compatibility authority when no retained owner binding exists. Therefore direct handleGatewayRequest plus a hand-built client cannot count as authenticated acceptance. We keep the genuine outer dispatcher/handshake binding as a hard unresolved requirement, rather than treating the presence of these internal checks as proof of authentication.

Original upstream source comparison uses only fixed commitbcfc88812a35243893585dbeca87ca41b48272ca and public source; final compiled bindings above use actual UK file hashes, not upstream guesses. The earlier404 lookup of a guessed runtime source path was corrected to src/gateway/server/ws-connection/authenticated-request-dispatch.server-methods.runtime.ts; no guessed compiled name was adopted.

## Disposal, persistence and recovery

The combined contract acquires once, validates real method ownership, gives the existing authenticated owner a guarded dispatcher, compares metadata through the inherited validator, and uses the existing immutable journal phases. It stops new admission when the owner returns/throws, waits all dispatched native promises, then lets the inherited finally release the inspection handle. Late native rejection prevents OBSERVED even if the owner returned metadata early. Stored dispatch references reject after owner closure/release. No Promise.race abandons a late native request; a stuck native request requires the separately bounded owner process/watchdog and stays UNKNOWN after termination, not automatic reacquisition.

Successful contract returns remain CONTRACT_ONLY; realLoader/authenticatedDispatch/CP11 NOT_EXECUTED and full compiledBinding UNBOUND. Native factory/handler callbacks in tests are explicitly fixtures. Actual source bytes are only read as data; not parsed by archived Babel, evaluated, imported or registered.

16 contract scenarios cover wrong descriptor scope/owner/profile/handler/duplicates, exact registry ownership, forbidden request/config authority claims, restricted method/params, native denial, owner failure, descriptor rejection after acquisition, release failure, closed-reference refusal, persistent readback/no reinvoke, completion drain and late native rejection. Real appendRecord/readRecords are used for lifecycle cases. Seven-file static regression verifies actual bytes, source mapping, getter/alias rejection and every-file tamper rejection; fixture namespace functions are never invoked.

## Concentrated remaining material/acceptance gaps

The report records0 missing original156 first-level names. Registry's3 direct relative imports and server-methods'53 direct references are present. Focused recursive literal analysis of registry/runtime/server-methods roots can read946 modules, reaches560 missing relative frontier paths,53 bare package specifiers and99 dynamic/resource-indicator modules. Full lists and edge inventory are delivered together. These are a conservative lexical cut, NOT an AST proof or a proven minimal executable closure; they do not justify transferring560 files or raising the previous16MiB cap. The input run itself recorded283 bounds and887 unprocessed entries.

| Minimal next binding/gap | Exact available evidence / bounded next scope |
|---|---|
| Real outer dispatcher + composition owner | Missing from current packet. Existing gateway-cli-DpWXmd4k.mjs → run-command-D-K_dOJ-.mjs is present; its literal next entry run-BNH_gC9b.mjs is absent here. Its SHA is UNKNOWN in this report. Original retained manifest/tar should locate this focused entry and the actual dispatcher anchor; no guessed alias, live-tree recollection or blanket larger packet. |
| Remaining import frontier |560 current boundary names are persisted, not called the final minimum. Resolve/filter against original retained manifest and actual native entry first; use only needed code for that entry and retain unresolved dynamic/exports/native policy. |
| Parser | Actual @babel/parser8.0.6 package and lib/index.js481329 bytes/SHAa6993b23a0d162cc93e49f72ef927c947c2026cd146cfe9c02cd695a4258411d are already present. No new parser request. Execution is NOT_EXECUTED by task scope. acorn8.18.0 is reported missing; it is not an automatic blocker requiring recollection when the existing Babel material is available. |
| Node/native/image | Original report binds Node126595440 bytes/SHA7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c. Node bytes themselves are NOT in this packet, so this is inherited report evidence. ELF interpreter /lib64/ld-linux-x86-64.so.2 plus libdl.so.2/libstdc++.so.6/libm.so.6/libgcc_s.so.1/libpthread.so.0/libc.so.6/ld-linux-x86-64.so.2 have no retained library candidates in the report. Actual image resolution/compatibility remains UNKNOWN; known5341f193… image proves Python3.11/UID1002 only. No runtime install/image pull is proposed. |
| Real authenticated call | Requires genuine isolated transport/handshake/profile/device-policy owner and fixed dispatcher import, then native metadata positive/negative/disposal/restart evidence. No hand-built clients or fixture result can close it. |

openclaw.mjs is the sole member reported absent from the original candidate's retained SDK manifest scope; do not mislabel it a copied-file failure. Its absence does not invalidate the existing registry/runtime source work. A selected native library entry may avoid using that CLI shim, but the actual genuine composition root must first be traced and bound, never invented as a replacement Gateway.

This delivery does not authorize another onsite operation. A later candidate must concentrate the exact retained-archive reads/outputs for the focused missing owner entry; do not rerun source collection, automatically widen caps, request files one at a time, change permissions, run SDK/parser or advance B6/B7/P3. B5 remains PARTIAL.
