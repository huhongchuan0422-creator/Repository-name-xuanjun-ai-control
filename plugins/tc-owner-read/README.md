# TC owner-admitted READ candidate (not enabled)

This is a native OpenClaw plugin source in the original TC release tree, not an
installed Gateway plugin, new identity provider or replacement task dispatcher.
No live configuration accompanies this candidate. Keep enabled=false/absent.
Load the plugin **from the reviewed complete TC release tree**: its fixed Python
consumer is ../../scripts/task_center_owner_read.py. Do not npm-publish or install
this directory alone and lose the exact sibling application dependencies.

## Named actual path

package.json/openclaw.extensions -> index.mjs default.register -> public
api.registerGatewayMethod('taskcenter.handoff.read', handler,
{scope:'operator.read',profileAccess:'required',sessionAccess:{mode:'read'}}).

The host router supplies client.authenticatedUserProfile and
sessionAccessAuthority.assertCurrent/retain. sessionKey selects only the
Gateway resource; it is never a person, TC principal, role or grant.
Shared owner, synthetic callers and sandbox-required sources are rejected.

The handler selects a pre-authorized host configuration binding, checks source
currentness and starts one fixed isolated-mode Python child with a private
inherited fd3 pipe. No shell, listener, permanent service, network endpoint,
external token or signing key. The pipe is custody by the spawning trusted
owner/OS process domain, **not** a general external authentication protocol.
No unrelated OS principal may gain service/DB access to make this work.

Python opens only the existing DB (mode=ro, query_only), borrows the original
SessionStore read shape without schema initialization, then calls original
CanonicalHandoffBackend -> HostIdentityProvider/HostActionAdapter ->
HandoffHost.read_receipt. Existing FORMAL profile, session, assignment, exact
handoff:READ grant, contract and original receipt checks remain mandatory.
No session login/create, INSERT, grant issue, task claim or event record.

The child computes privately. The only external READ effect is the Gateway
respond call: the owner checks its original lifetime again immediately before
releasing buffered output. Source abort kills the child and suppresses output;
all paths release the retained borrow. Child error/timeout is a fixed denial.
This is why no distributed SQLite/Node write transaction is required for this
READ path. **Do not extend this pattern to write effects** without an explicit
same-owner write-admission, durable idempotency and reconciliation contract.

## Host configuration (data contract, no production values)

Keys: enabled, python (approved absolute interpreter), database (existing DB),
runtimeConfig (original protected handoff runtime selector), dispatchConfig
(original protected dispatch selector), bindings.
Each binding has gateway_profile_id (canonical authenticated person), tenant_id,
principal_id, session_hash (existing TC session reference), task_id, attempt_id,
expires_at (maximum approved lifetime). Mapping data comes only from the
existing lawful source/host owner, never method params or role labels.
The child rechecks the original DB row and grant; a mapping is not a grant.

Request keys exactly: sessionKey, task_id, attempt_id, event_id, operation_id.
operation_id is correlation only, not authority. The response echoes it and a
request digest with the original receipt. Repeat READ is naturally safe and
revalidates source and canonical permissions; **no response/authority cache**.
A lost/error result can repeat the same READ, never substitute a write action.
There is no second ledger or durable request registry. A process restart drops
all retained source handles; new requests require fresh host admission.

## Runtime acceptance still required

Independent review, original lawful profile->principal/session binding, an
existing authorized handoff:READ grant, service identity's already-approved
read access to the original selectors/DB, and supported host plugin loading
remain prerequisites. This source neither enables the plugin nor modifies the
runtime profile, selectors, filesystem permissions, Gateway install or DB.
If existing OS access is insufficient, enabling this transport would need a
specific runtime access decision; do not sudo, move the DB or open a daemon.

Test: node --test tests/owner_read_gateway_delta.test.mjs (from TC root).
This invokes the registered handler and real fixed Python child over actual
private pipes against synthetic SQLite fixtures. Host authority/registration
are controlled isolated fixtures, **not an authenticated live Gateway probe**.
