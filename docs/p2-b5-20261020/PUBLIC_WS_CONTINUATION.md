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

[evidence/p2-b5-ws-20261021/static-edges.json](../../evidence/p2-b5-ws-20261021/static-edges.json) records all exact literal edges against the existing1718+3 files. New direct missing source edges:message-handler30 of113,ws-connection22 of45,run35 of93. These overlap and are lexical boundaries, NOT a minimal executable closure or authority to fetch all of them. Suspicious regex tokens are kept as ambiguous, not real package names. No archived AST parser was run.

| Remaining item | Current evidence / exact limit |
|---|---|
| Native connectionWork owner/drain implementation and immutable source binding | Actual params.connectionWork.track/trackCleanup/registerConnection calls now read. Owner implementation is not defined in these3files; cannot invent drain(), return fake drained flags or release early. Need genuine composition owner/provider code from retained material before runtime wiring. |
| Public entry transitive imports/resources | Direct source edges captured; unresolved dynamic imports/export conditions/native modules persist. No560 blanket request or increased bound. Use retained manifest to choose a later approved minimum candidate if necessary. |
| Runtime bytes/image compatibility | Inherited report binds Node126595440/SHA7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c, but Node/shared-library bytes and compatible image evidence not delivered in these3files. Python-only image evidence cannot prove Node compatibility. |
| Real transport/authentication acceptance | Needs genuine isolated socket/handshake owner, original profile/device/current-authority chain, no-model metadata positive+refusal, tracked cleanup/disconnect and release/restart evidence. All NOT_EXECUTED. |

B5 installation time cannot be promised before exact closure/native-owner/runtime candidate is frozen and separately confirmed. This source increment removes the wrong private-export seam but is not an executable UK installation operation. No new onsite command or permission request hidden here; B1–B4 stay inherited.
