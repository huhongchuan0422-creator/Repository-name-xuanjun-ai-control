# Default-off approved-object queue integration

## 1. Scope and responsibility

Base: 23b780f46bb3ed08f3bf3f6454c200cdc3a9ca70, original connection branch and Writer. This change closes the mismatch between queue.py rejecting fetch_approved_object and private_transfer.bound_job requiring its real SUCCESS/InvokeId. It does not enable production reads, approve a catalog, grant project.files.read, deploy a service, or change the frozen 23b domestic CSP upgrade candidate.

The original B5 analysis input has 19 metadata-bound objects totaling 93592 bytes (largest 53969): five historical protected archive members and fourteen live installed package JSON objects. The implementation caps count/total/single size at those bounds, but contains no real B5 recipient, root, catalog approval or executable production request. This is not the final installation closure. Existing 828 received bodies are not recollected. Original 16MiB project / 2MiB single source / 18MiB package limits are not enlarged.

## 2. Minimal implementation

ApprovedObjectsPolicy lives in existing fixed_actions.py. Runtime optionally loads only /etc/xuanjun-cloud-executor/approved-objects-binding.json through the existing protected root-owned 0600 reader and an exact host-config SHA. Missing optional configuration yields None. The binding contains a canonical catalog and its SHA, project budget policy, precise roots and owner UIDs, a single recipient, a one-to-one object-to-request-ID map, execution user/UID and exact private_transfer.py reader SHA. No request can supply a path, command, identity or enable switch.

Queue submit and dispatch both validate the injected policy. Worker dispatch/result use dedicated branches, never the old OS probe fallback. DISPATCHING commits before the cloud call; missing/uncertain InvokeId stays UNKNOWN and is never redispatched. The sealed conn-second-window-uk-20261021T162627Z is forbidden.

The generated fixed command reuses only check/stamp/directory/read_object from the hash-verified existing transfer module. It checks host, UID and request/catalog validity before reading and checks expiry again before emitting. It reads only one approved regular file using the original NOFOLLOW descriptor and full-SHA algorithm. Stdout contains only bounded identity/object metadata. No body, base64 body, arbitrary exception output or private destination is returned through cloud output. The generated collector catches identity/read/output failures and exits 2 without printing exception text; failure receipts reject non-integer or out-of-range exit-code payloads.

A real matching successful invocation, integer exit 0, exact instance/InvokeId/host/UID/nonce/catalog/object/recipient/length/SHA permits an original queue SUCCESS receipt. Result returns data=None, so the public result path/file_sink is never used. This metadata SUCCESS is not body delivery. Original export_chunk independently rechecks authorization, validity, original SUCCESS and the actual locally accessible protected source root; Receiver remains responsible for private custody and reconciliation.

## 3. Explicit remaining live bindings

The worker's cloud check runs on UK, while export_chunk reads on the resource process's machine. A cloud success does not create/mount a source root or prove the receiver root exists. Both locations and protected ownership must be actually enrolled. This implementation does not extract archives: the five historical members cannot silently be replaced with live files or unpacked into a newly invented root.

GitHub task actor and OAuth recipient are separate bindings. The current github:332398908 subject is not a catalog TOKEN-form recipient ID; an approved protected mapping is required, not a relaxed parser. Current cloud-connection-acceptance project/catalogs=[] and connection.status-only grant are unchanged. The B5 Work recipient and receiving root are not inferred from a workspace label.

Actual activation needs one precise approval covering the nineteen inert bodies, recipient/project, source and receiver roots/identities, registered operation and service deployment; any OAuth project.files.read grant requires its own applicable exact consent. No production values or approval fixtures are shipped. The default-off module can be reviewed/tested independently of those remaining live decisions.

## 4. Verification and recovery

Synthetic tests cover actual Queue/worker state transitions and original bound_job/export_chunk contract, plus default-off submit/dispatch/query, binding/hash/target/actor/recipient/request-ID/window/budget rejection, strict output fields/numbers/JSON, uncertainty/no replay, metadata-only command and before-read expiry/identity guards. Mock export tests do not prove a real source root or body delivery. Existing OS operations and website policy retain their interfaces. No schema change, credential or production SUCCESS is created by this source change.

Hosted uses the existing test_cloud_connection*.py discovery on Python 3.6.15, 3.12.15 and exact domestic 3.11.6; no workflow, secret, runner or deployment trigger is added. Local legacy tests requiring /root can be unavailable; failures/skips are recorded, not counted as pass. Source tests do not imply Hosted or deployment success until the exact commit's results are read.

Runtime code_pin already includes all four changed executable modules. The OAuth source manifest updates their existing entries without changing its 30-member set. Old installed pins/releases and the separately frozen 23b candidate remain valid only for their original bytes. No old enrollment installer is run on this candidate. Deployment and rollback need a future exact closure/config binding; default-off preparation is not activation permission.
