# B5 public WS entry increment — still PARTIAL

Along1d22f20f / PR17#6307973862, reuse daa83aed registry method adapter and inspectReadonlyLease journal. No new installer/CLI, server operation, B1–B4 reinstall or SDK/parser execution.

## Actual receipt, not delegated verification

This window obtained materials (2).tar and report (1).json through normal existing attachment access. Local full-byte SHA matched358400/facbffc113f7449470721f09e5c1a227ab016b647abf7cb9fd02cc2fe35cc50c and1646/70f8855c159ca71bddf7e16a69fbdc4aeda56f6e01138784ffc0c553a8ecc87a. Three unique safe regular members match exact names/bytes/content SHA and report set:run122958/55673f688f7e455cd1bfdaf6a0f26270ff5e6565881403c1b066a82530ab810f;message-handler176118/ff332fdec514638bdd1655a510a7544f5b9a848eccf11c951851b97e192410f0;ws-connection48210/b51e1190bd1ca47b2497311e798ee95c2d7acd1e1a410bc6f6c1b1aeb5862f53. No further request for old packets or recapture.

## Read actual compiled public interface

message-handler-DKklmnFX.mjs L274 declares internal createGatewayAuthenticatedRequestDispatcher. L3373 attachGatewayWsMessageHandler(params) builds it internally with handler=params. L3413 detached handshake and L3676 incoming processing enter params.connectionWork.track; L3683–3712 handshake queue is flushed after tracked processing and the public call returns onMessage. L3715 exports only attachGatewayWsMessageHandler. Therefore a fulfilled/void onMessage return does not prove request completion. ws-connection-CsJ9cE0L.mjs L102–135 is on-demand loader/queued frames; L455 tracks socket-close cleanup and releases the connection registration afterwards. Its original lazy-loader wrapper is not copied or bypassed by a pretend implementation.

The new b5_ws_public_contract.mjs is a trusted-root CONTRACT seam for that public exported function. bindPublicWsNamespace verifies exact three buffers plus inherited package.json/version2026.9.9, requires own data export attachGatewayWsMessageHandler, and returns STATIC_BYTES_BOUND_ONLY / runtimeProvenance UNBOUND. No guessed internal alias/export, dynamic SDK import or copied internal dispatcher.

withPublicWsContract reuses inspectionMethodRegistry and inspectReadonlyLease. It preserves exact original socket, connectionWork, getClient, context and policy object references; changes only per-request getMethodRegistry and response observation callback. No client/scopes/auth policy/context generation. Public attach registers native onMessage; the same socket registration is replaced with a small metadata/connect admission guard that forwards original bytes unchanged, without copying native handshake/dispatcher code. Genuine connect frames reach native handshake only when original getClient has no client. Metadata requests remain governed by native queue/auth/policy; invalid actions close the existing transport and yield no OBSERVED. No hand-filled client or scopes establish identity.

Response acceptance requires correlated exact request ID, one native sent/ok response and inherited metadata validator. The callback return is ignored. On owner return/error, detach adapter ingress, then await trusted owner quiesceAndDrain including native handshake queue, all tracked work and trackCleanup. Only then may original lease release run. Attach failure also requires owner cleanup/drain of partial listener/work. Failed/unknown drain suppresses original release and RELEASED, leaves recoverable journal HOLD. No promise race, new invocation or forced cleanup occurs. A stuck drain stays pending; separately bounded owner process remains required before real execution.

IMPORTANT: this delivery does not supply or authenticate the actual native owner/drain implementation; its compiled source/provider binding remains UNBOUND. A callback resolving undefined is a contract result, not runtime evidence. A boolean/object PASS is rejected. SDK namespace injection, EventEmitter fixture and drain fixture cannot prove real handshake or work lifetime. Existing old internal-dispatcher contract remains unchanged as prior limited evidence; this new public seam is the candidate path for later actual owner integration.

## Tests and source data

13 targeted local tests: actual3 source+package byte binding, each member tamper rejection, private-only namespace rejection, queued-handshake scheduling, delayed void-return request, native refusal, disconnect response, partial attach failure, drain failure (zero early release), forbidden action, missing response. Lifecycle scenarios use real immutable appendRecord/readRecords; scheduling callbacks are explicitly fixtures, not SDK/auth execution. Actual source buffers retained compressed as static test DATA with existing upstream MIT license in ../evidence; no eval/import/archived parser. Hosted run and exact source commit are recorded in PR17, not inferred from local tests.

## Concentrated remaining dependencies, not a new collection request

[evidence/p2-b5-ws-20261021/static-edges.json](../../evidence/p2-b5-ws-20261021/static-edges.json) records bounded lexical literal candidates against existing1718+3 files (not all AST edges): message-handler-DKklmnFX.mjs: 30 unavailable / 113 relative candidates, run-BNH_gC9b.mjs: 36 unavailable / 94 relative candidates, ws-connection-CsJ9cE0L.mjs: 22 unavailable / 45 relative candidates. Static from/side-effect imports, dynamic imports and require are searched separately with matching quote delimiters, avoiding cross-quote consumption. These overlap and are not a minimal executable closure or authority to fetch them all. No archived AST parser was run.

Actual run-BNH L2362 imports ./server-ChnNHwLm.mjs; L2376 takes startGatewayServer from that module. This exact server composition source is absent from current1718+3 bytes. It is the focused next composition-owner source dependency, with manifest-bound4051 bytes/SHA25626067e9a59a2addaeb05f39945dee9a42dc7ae9d22f6de530fc6f1d5ce25ae56 (file bytes not yet received). Do not guess a replacement server or claim owner/drain source is available.

| Remaining item | Current evidence / exact limit |
|---|---|
| Native connectionWork owner/drain implementation and immutable source binding | Actual params.connectionWork.track/trackCleanup/registerConnection calls now read. Owner implementation is not defined in these3files; cannot invent drain(), return fake drained flags or release early. Need genuine composition owner/provider code from retained material before runtime wiring. |
| Public entry transitive imports/resources | Direct source edges captured; unresolved dynamic imports/export conditions/native modules persist. No560 blanket request or increased bound. Use retained manifest to choose a later approved minimum candidate if necessary. |
| Runtime bytes/image compatibility | Inherited report binds Node126595440/SHA7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c, but Node/shared-library bytes and compatible image evidence not delivered in these3files. Python-only image evidence cannot prove Node compatibility. |
| Real transport/authentication acceptance | Needs genuine isolated socket/handshake owner, original profile/device/current-authority chain, no-model metadata positive+refusal, tracked cleanup/disconnect and release/restart evidence. All NOT_EXECUTED. |

B5 installation time cannot be promised before exact closure/native-owner/runtime candidate is frozen and separately confirmed. This source increment removes the wrong private-export seam but is not an executable UK installation operation. No new onsite command or permission request hidden here; B1–B4 stay inherited.


## Next independent increment after a01251a6

20 local/Hosted-targeted contract cases now include5 anomalous drain return values(false,true,null,object,zero): no original release/RELEASED/OBSERVED. Undefined is only the internal callback contract, not native proof. Delayed handshake/request plus cleanup which schedules further cleanup must all settle before release. Captured old ingress callback throws during drain and after release, with no new tracked work. Successful synthetic contract output now explicitly includes executionReadiness HOLD_REAL_OWNER_UNBOUND. No compiled/native drain implementation has been invented.

The fixed4051-byte server member is absent from both locally verified material sets; exact-name attachment search also has no file-byte result. Its manifest pin is known, not UNKNOWN. A one-member retained archive candidate is documented in SERVER_MEMBER_CANDIDATE.md; only separate onsite confirmation may permit it. No80-file/560-file request is made.


## Received-source lifecycle alignment after1fa440b8

The original twenty cases are retained and NOT_RERUN by this increment. Workflow now runs only the9 newly affected close/drain cases; no prior tests are deleted or relabeled as new results. Real SDK/owner/installation remain NOT_EXECUTED/UNBOUND.

Source-backed gap fixed: adapter previously detached ingress then called an unspecified quiesceAndDrain. It now calls the ORIGINAL per-connection params.close(1000, reason) explicitly after ingress removal, and awaits the trusted owner's complete drain before setting drained=true or allowing original lease release. A void close return is not drain proof. Close errors or non-void close return still attempt drain, but retain HOLD and suppress original release/OBSERVED/RELEASED. No generic abort/registration replacement or native cleanup implementation is invented.

| Stage | Actual received source binding | Adapter obligation |
|---|---|---|
| Stop own ingress | message-handler onMessage queue and ws-connection isClosing checks | Detach only adapter guard; retained guard refuses after stop. Do not set shared connectionWork.isClosing. |
| Close original connection | ws-connection L260–280 retireTransport→closed=true→connectionController.abort→transport cleanup;closeWithGrace→retireConnection→closeGatewayTransportWithGrace | Call original params.close, preserve socket/context/client authority. Do not abort global work.signal or implement transport close. |
| Track normal/handshake work | message-handler L3413,L3676;ws-connection L113 on-demand loading | Native connectionWork.track remains exact owner object; onMessage void and isClosing are not drained evidence. |
| Track socket cleanup | ws-connection L453–458 socket.close listener→connectionController.abort→connectionWork.trackCleanup(handleSocketClose).catch(...).finally(releaseConnection) | Wait cleanup and releaseConnection completion, including later enqueued work, using real owner drain once its implementation is received. |
| Connection registration | ws-connection L281–283 registerConnection(original close callback) | Do not create a second registration or call unregister early. releaseConnection is distinct from plugin lease.release. |
| Abort scope | message-handler handler.connectionWork.signal;ws-connection L190,L263,L454,L475 connection-local controller/next.connectionSignal | Aborted signal is cancellation only, never proof of request or cleanup completion. |
| Lease release | Original inspectReadonlyLease finally, gated by adapter drained flag | Drained true only after original close and owner completion; otherwise leave journal/handle uncertain HOLD. |

Exact source callsites with member SHA and line literals: evidence/p2-b5-ws-20261021/connection-work-calls.json. This is static inspection of real bytes, not a copied owner implementation or SDK execution.

Nine new cases: normal delayed cleanup;already-aborted/isClosing still waits;close throw;close false;close object;drain throw;drain false;successful real-journal adapter close→asynchronous cleanup→registration retirement→drain→lease release;uncertain-close real-journal adapter retains handle and suppresses success/release. Retained guard is rejected during and after drain. Cleanup/tracker functions in these scheduling tests are explicit fixtures, with no authentication or native owner claim.

Current true byte dependency is unchanged: same existing10240-byte tar/SHAf9cf2764f46910d1be1bc8209fe533b6416e4f21c521bcc3c85489f02470dd52 and936-byte report/SHA0800cf8dde686b3b27fd2f2c47ac97dce04671e6cd96bb60dead5ed4135d7ab0, containing server-ChnNHwLm4051/pin26067e9a59a2addaeb05f39945dee9a42dc7ae9d22f6de530fc6f1d5ce25ae56. UK generation already succeeded. No new source filename can be inferred before reading that file. Transfer existing raw attachments only, not re-capture. Once read, follow actual composition owner rather than all lexical edges.

Installation remaining: (1) receive/hash existing one-member source;(2) bind native connectionWork creation/quiesce/trackCleanup/drain from its actual composition chain, only subsequent indispensable byte gaps may be named;(3) close Node/native/image dependencies and freeze bounded isolated final operation/recovery candidate;(4) separately confirmed real loader/authenticated metadata/refusal/disconnect/drain/recovery evidence. Only the source increment ETA is30minutes; no honest installation ETA exists until owner implementation and runtime dependency bytes are known. No additional global review is initiated.


## Received real server root (supersedes the earlier waiting-for-transfer status)

Both existing attachments are now actually received: materials (3).tar 10240 bytes / f9cf2764f46910d1be1bc8209fe533b6416e4f21c521bcc3c85489f02470dd52; report (2).json 936 bytes / 0800cf8dde686b3b27fd2f2c47ac97dce04671e6cd96bb60dead5ed4135d7ab0. The sole regular member server-ChnNHwLm.mjs is4051 bytes and matches26067e9a59a2addaeb05f39945dee9a42dc7ae9d22f6de530fc6f1d5ce25ae56. Real member bytes are persisted as inert base64 evidence, never imported/evaluated. Static binding helper fails closed on any byte/size/type change and explicitly retains UNBOUND. Prior lifecycle9 and WS20 tests are unchanged and not rerun.

Actual call chain: run-BNH_gC9b dynamically imports server-ChnNHwLm → public startGatewayServer → startGatewayServerWithRuntime → readOnlyWorkers.run / withAgentDatabaseStartupAdmission → loadServerStart → dynamic import ./server-start-Bz-KV48j.mjs → mod.startGatewayServerCore(port,opts). This wrapper does NOT define connectionWork or its drain API. It owns optional gateway lock release; wraps close through readOnlyWorkers then broker/admission then owned lock. Those server-level resources are distinct from per-connection registration and plugin lease; do not substitute wrapper.close for a proven connection-work drain or start it to inspect.

Minimum next implementation byte gap: dist/server-start-Bz-KV48j.mjs (literal direct dynamic import at server root line13; core call at line53). Not present in the verified1718 materials, three WS files, or received single-member bundle. Its size/SHA are NOT present in the received selected-member reports; UNKNOWN, no guessed pin. Obtain that member's exact existing-manifest row and bytes from the already retained archive via a separately frozen/confirmed bounded candidate, not a new full capture. No80-member request. Its own source may identify a further owner module; that is not yet read and cannot be named as proven.

True remaining installation prerequisites: actual native connectionWork creator/quiesce/connection-close/cleanup-drain bytes and binding; Node/shared-library/image closure; real isolated loader/authentication/readonly positive+refusal and disconnect/recovery candidate. Native SDK/authentication/install remain NOT_EXECUTED, owner UNBOUND and closure UNKNOWN. This increment is static byte evidence and regression, NOT final executable installation permission. No UK operation or SDK execution occurs.
