# P2 Work UK transport handoff — protected caller candidate

Delegation: PR58#6228357313 and exclusive stop confirmation#6228383533.
Only the six delegated new paths are changed. Eight existing paths, private
completeness implementation, original unpublished diagnostics and P2 writer
remain with the original execution owner. Prior accepted unchanged algorithms
inherit their exact audit versions; new caller changes require incremental review.

## Scope

The only remote command is a fixed stdlib identity statement; it cannot read
Seed/history Seed/Plan/Packet, import P2 applications or install services. Target:
eu-west-1 / 40dfc6a47d5e4363b9da7d0d6ab01cb1 / iZd7oeikknn1z21sq6ji6zZ,
role acs:ram::1107191612880779:role/xuanjun-ai-esc. Public success explicitly
carries p2_accepted=false and private_inputs_read=false. It proves transport
identity only, never private completeness, Schema3 or installation acceptance.
The blocked original private diagnostic package is not included or re-encoded.

## Fixed protected entry

The module now has only two CLI actions, run-once and query-existing. No command,
host, credential, policy path or script path can be supplied as CLI input.
Execution requires real/effective uid0 and pre-existing protected files:
/etc/xuanjun-p2-swas/TRUST.json, WRITER_EPOCH.json and CREDENTIALS.json.
All are Root:Root 0400, regular single-link bounded files, no writable or linked
ancestors. No code enrolls trust, generates real credentials, creates the ledger
or transfers canonical writer. The key file contains only AccessKeyId and
AccessKeySecret; it is read only after policy gates. No key text is logged.
This path is an explicit prerequisite, not a claim these files currently exist.

TRUST binds a separately verified exact approval-body SHA and independent
reviewer/source identities, approval comment ID, exact canonical binding,
writer-epoch SHA, code paths and the one persistent ledger path. The actual
canonical epoch provenance must be established by the original P2 writer;
an invented local EXCLUSIVE record is not authoritative. Root ownership and
matching strings cannot themselves prove independent custody. That remains
external evidence, not a developer-generated fixture or permission.

Binding includes operation RUN_COMMAND or QUERY_EXISTING, attempt, nonce,
UK target/role, exact command SHA, both installed source hashes and epoch SHA.
Only separately issued P2_UK_TRANSPORT_ONCE approval with exact binding,
UK_TRANSPORT_APPROVED, <=2h integer validity, max_attempts=1 and false private
read/install permissions is accepted. GitHub fetch checks the fixed API origin,
repository, PR58 issue URL, comment ID and numerical author ID/login, disables
redirect/proxy and bounds output. GitHub author identity is supplemental; the
protected independent body-hash registration provides approval authority.

A local exclusive flock covers policy, epoch, installed code and approval checks,
STS and dispatch. Policy/epoch/comment are rechecked after STS. Ledger inode is
bound to its approved root-owned path. A consumed dispatch intent refuses new
credentials or RunCommand. A new QUERY_EXISTING permit is explicitly operation
bound, requires the exact saved attempt/nonce/InvokeId and consumes an immutable
query-permit-{comment ID} marker. Reusing it is rejected. Poll never dispatches.
Fresh permission is necessary after an uncertain consumed query; deleting or
changing ledger paths to bypass consumption is prohibited.

## Persistence, network and process bounds

The held private directory fd and immutable O_EXCL/NOFOLLOW 0600 records fsync
file and directory. dispatch-intent is durable before RunCommand; InvokeId is
saved before querying. Unknown submission or failure before saving InvokeId
keeps intent consumed; it cannot be blindly resubmitted. Accepted/rejected
terminal receipts remain immutable. Public output/error schema never includes
raw API bodies, private material, URLs with credentials or client exceptions.

AuthenticatedRPC uses fixed HTTPS POST endpoints, HMAC signatures, bounded
response and request timeouts, a monotonic admission deadline and no retries.
A supervisor forks the actual entry into a process group, waits <=240 seconds,
and kills/reaps that child/group on timeout or interruption. Pending cloud work
may outlive the local controller: timeout is UNKNOWN, never proof cancellation.
Saved InvokeId is queried under a new exact query permit; missing ID requires
separate investigation. The supervisor does not automatically restart anything.

Polling remains bounded by query count and the supervisor; live API backoff/rate
policy, actual durable filesystem and complete interruption matrix still require
target acceptance. Kernel uninterruptible I/O is not claimed to be cancellable
by a userspace timeout. No production interruption guarantees are inferred from
one hosted fork timeout test.

## Trigger and private delivery boundaries

The GitHub workflow has push and workflow_dispatch for OFFLINE TEST/BUILD ONLY.
It has contents:read, no Secrets references and no host call. Hosted sudo is
used solely for disposable /root test fixtures, never UK access. This declaration
neither adds a dispatch tool to the chat session nor enables production execution.
Actual platform trigger capability remains unavailable here. No old probe rerun
or push-triggered live action substitutes for a fresh exact permission.

The protected caller must be installed at pinned root-owned source paths by a
separately approved mechanism, supplied with authentic policy/epoch/credentials,
and connected to an approved event source before any real call. None of these
has been installed by this source change. The current transport boundary does
not solve private Seed/Plan/Packet delivery. Originals stay in UK protected
storage, authenticated private recipient remains unverified, and the original
TTY/dual SHA requirements cannot be emulated or silently waived.

## Evidence

42 local methods pass: original20 transport/receipt, previous11 adapter/gate,
new8 real-Root temporary-file entry tests and3 provenance/fork-supervisor tests.
The real-Root fixture imports exact source copies under a temporary /root tree,
validates actual modes/hashes and exercises dispatch then separately authorized
query with synthetic RPC. Tests cover epoch, source, ledger and credential drift,
post-STS approval changes, duplicate request and query consumption. A real fork
is killed on timeout. Synthetic network responses and keys are not UK evidence.
Hosted CI separately runs this exact code; Python3.6 AST is not 3.6.8 runtime.
Manifest binds all six source paths and test log in an eight-member TAR.

P2_RELEASE=HOLD; SCHEMA3_APPROVAL=NO; C_INSTALL_AUTHORIZATION=NO.
No real UK STS/SWAS call, live InvokeId, private-data transfer or production
installation is implied. Prior accepted source is not needlessly re-reviewed;
new entry, operation binding and affected call chain are the incremental scope.

Direct isolated Python execution loads only the adjacent root-protected receipt module, never CWD/PYTHONPATH. A real isolated subprocess negative test verifies missing sibling refuses without importing an injected scripts package. Actual installed CLI happy path still requires authentic protected configuration.

The isolated bootstrap rejects nonregular/oversized/multilink receipt code before reading/importing; a real FIFO subprocess regression proves no blocking read occurs.


## 2026-10-17 durable recovery implementation checkpoint
Migration window receipt PR58#6229032550 establishes manual-only trigger,
no available dispatch tool, existing step-level Repository Secrets injection,
and no UK persistent consumption service built by that window. No secret value
or repeated Owner setup is required.

The transport now classifies persisted dispatch checkpoints under its existing
lock and before credential access. Empty state grants no authority; an intent
without InvokeId is consumed UNKNOWN; a saved InvokeId only permits a separately
authorized query; terminal or contradictory/corrupt records reject replay.
Recovery is read-only: it never clears records, adopts an unknown object, repairs
JSON, generates approval, or sends a replacement RunCommand. Reopened directory
FD tests exercise restart reading of the same persisted bytes.

This implements recovery classification on an already provisioned protected
filesystem, not a cross-host consumption service. No persistent host path has
been provisioned. Actions trigger wiring, remote durable admission protocol,
actual writer epoch and authentic trust enrollment remain incomplete/UNKNOWN.
No cloud API or UK host was used in these tests. No production permission is
inferred from this checkpoint. Consolidated independent review waits for the
complete affected chain; previously accepted unchanged code is inherited.

## Split-environment identity receiver candidate
`consume_remote_identity` implements the UK-side identity-only protocol without
cloud credentials. Actions must submit an exact request already bound by a
protected target policy; the target requires its existing ActivationStore and
BrokerObservationClient, plus the protected approval verifier. The receiver
reads ACTIVE before and after BROKER_OBSERVATION and binds the original task,
lease owner/unexpired lease, Fence, generation/epoch/instance/ledger UUID and
canonical paths. It never grants a lease or starts the original mechanism.
Inactive activation is HOLD, including for the initial identity test.

An existing protected persistent ledger records remote-intent before identity
measurement and remote-result after rechecking gates. Missing result is UNKNOWN,
not permission to rerun. A repeated exact request can only replay validated
stored bytes under still-valid authority. These files track transport receipt
consumption only; they are not another canonical task/writer registry. Local
lock and read-only observation do not grant global writer exclusivity.

This is a callable candidate API, not an installed factory or remotely enabled
CLI. Target provisioning, protected request/approval adapter, authenticated
Actions-to-target envelope, cloud receipt binding and actual event trigger are
still incomplete. The existing run-once CLI remains the co-located candidate;
it has not silently switched to this protocol. No arbitrary remote command or
application code is executed by the new receiver. All eight new tests use
injected activation/observation/approval fixtures; they are not UK evidence.

## Complete split-transport candidate — 2026-10-17

This section supersedes the earlier incomplete adapter checkpoints. It describes
implemented code and an installation proposal, not a deployed service or grant.

### Entrypoints and credential boundary
- The workflow keeps push-triggered **offline** CI. A separate `protected-uk` job
  runs only on explicit workflow_dispatch, a non-offline choice, the fixed repo,
  Owner numeric actor ID, the explicit enable variable, and the named environment
  `p2-uk-transport`. Ordinary push cannot enter this job.
- `remote-run` and `cloud-query` use isolated Python on Actions. The initial
  adjacent-module loader validates source pins from the environment policy;
  the entry then validates exact commit/ref/workflow/source pins and a new,
  independently anchored `P2_UK_SPLIT_ONCE` approval. No checkout token is retained.
- Existing ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET stay in Repository
  Secrets and are injected into the protected step. The cloud code reads them
  only after approval and durable intent/permission consumption. STS uses the
  original fixed UK role; the adapter only exposes UK RunCommand and result GET.
- SWAS sends fixed shell words invoking
  `/usr/local/libexec/xuanjun-p2-swas/transport.py receive-identity` with bounded
  base64-encoded JSON on stdin. The JSON is data, not Python/shell source. No
  arbitrary command, configurable executable, credential, or private document is
  sent. The fixed target process uses Python -I -B and the timeout supervisor.
- The UK entry reads only its pre-enrolled Root REMOTE_POLICY.json, loads five
  original pinned modules (activation, projection, read transport/client, server
  identity), and invokes the original mandatory authenticated broker observer.
  It never calls root_broker.build/serve, activates a socket/unit, opens the task
  database itself, creates a lease, or writes a new writer authority.

### Exact policy and approval contract
Actions policy is registered as P2_UK_SPLIT_POLICY in the protected environment;
P2_UK_SPLIT_LIVE_ENABLED must remain unset/false until deployment approval.
The policy requires enabled/revoked flags, independent reviewer and source-writer
principal identifiers, custody_evidence_sha256, exact approval comment ID/full
body SHA, workflow_ref, request and binding. These are protected **registrations**,
not independent facts that source can manufacture. GitHub account or distinct
strings alone do not establish genuine independent custody.

The new approval body purpose is `P2_UK_SPLIT_ONCE`, decision UK_SPLIT_APPROVED;
exact binding, issued/expires (at most two hours), max_executions=1,
install_allowed=false and private_inputs_allowed=false are mandatory. Old
transport, TTY, preparation, Schema3 or installation approvals are not reused.
RUN and QUERY are separately approved operations. Binding contains operation,
attempt, request/command SHA, source commit, two code SHA, workflow SHA, fixed
host/instance/region/role, target_config_sha256 and exact invoke_id (empty only
for RUN). Approval and revocation are checked again after STS and before result
publication. Query's fresh permit may reconcile an expired original request,
but cannot execute that request again.

The request is the existing bounded UK_READONLY_IDENTITY structure. Its
approval_sha256 field is an opaque prior content/reference digest; it is NOT the
hash of the enclosing execution permit (which would be circular), nor proof of
trust. Root policy contains the exact request plus target_code, runtime_files,
activation_paths and ledger_path. Hashing these five fields yields the approved
target_config_sha256; this avoids self-referential configuration hashes. Root
checks exact current installed code/closure and policy bytes at each gate.

### Durable cloud journal and target receipts
The GitJournal uses dedicated `refs/heads/p2-transport-journal/<attempt>` and a
single state.json blob. This is transport consumption metadata, not another task
queue, task DB, epoch authority or business writer registry. Its one-use claim
is GitHub's atomic ref creation; later checkpoints are one-parent, non-force
fast-forward commits. A stale append is rejected. Unknown API writes are not
retried and never permit another cloud dispatch. Git commit/ref availability,
retention and permissions require actual admission evidence. Admin deletion or
history rewriting is outside the trust model; target intent remains a second
independent barrier. Actions concurrency and uploaded artifacts are not used as
the consumption authority.

| Durable observation | Allowed next action |
|---|---|
| No cloud record | Only exact approved RUN may attempt atomic claim |
| CLOUD_DISPATCH_INTENT, no ID | Cloud outcome UNKNOWN; never resend or guess ID |
| CLOUD_DISPATCHED / CLOUD_QUERY_UNKNOWN with ID | Fresh QUERY permit; query only saved exact ID |
| Query permit already recorded | No replay; failed/unknown query needs new explicit query authority |
| Cloud Pending/Running/Stopping | Preserve query-unknown; no new target command |
| Successful cloud result, target missing result | TARGET_EXECUTION_UNKNOWN; no repeat execution |
| Valid target result | SPLIT_TRANSPORT_VERIFIED, still p2_accepted=false |
| Rejected/failed target or malformed output | HOLD/terminal failure; no new RUN |
| Target intent without result | Persistent UNKNOWN; never auto-complete or remeasure |
| Target complete receipt | Read existing bytes only under still-valid target authority |

Root target storage is a pre-provisioned root:root0700 per-attempt directory.
remote-intent.json and remote-result.json are O_EXCL0600 with fsync; remote.lock
uses the same pinned directory. No automatic directory creation, deletion,
record repair or UNKNOWN reset exists. Historical cloud result querying does
not assert that the original lease or current writer remains valid today.

### Existing writer and endpoint trust
Only existing ACTIVE ActivationStore + authenticated BROKER_OBSERVATION are
used. They must agree on original task, live lease owner/expiry, Fence,
ledger UUID/generation/epoch/instance and canonical paths, before/after read.
The fixed Root-manager server-identity policy and measured endpoint delivery
remain mandatory. No owner/epoch is inferred from ps, local locks, fixture data,
old epoch2/7 receipts or a source-writer's approval string. Original PREPARED,
missing activation/socket, expired lease, unknown writer, unknown custody, or
unavailable broker means HOLD. This transport cannot bootstrap or activate P2
just to make its own test pass. Read observation is not a global writer grant.

### Exact installation / rollback proposal (NOT authorized)
1. After separate exact preparation approval, confirm no conflicting writer or
   unknown cloud operation and record existing path identities/hashes. Do not
   modify the eight original P2 paths, canonical DB, old masks or Fence.
2. Stage the approved transport.py and adjacent p2_swas_receipt_validator.py in
   root-controlled storage; verify exact source hashes and Python3.6 runtime.
   Target directory `/usr/local/libexec/xuanjun-p2-swas` root:root0755; files
   root:root0444; policy directory `/etc/xuanjun-p2-swas` root:root0700 and
   REMOTE_POLICY.json root:root0400. Existing objects must match an approved
   baseline; refuse silent replacement. No systemd unit is added by this code.
3. Register real policy/custody through the authorized Owner channel. Resolve
   actual already-installed immutable runtime paths and original activation
   descriptor/journal/lock from the canonical installation; pin all five module
   bytes. Do not use repository fixtures as production inputs. Provision the
   exact per-attempt directory, not a second canonical ledger or cloud-key file.
4. Stage only the reviewed workflow/ref through the repository's normal review
   protection. Register its manual entry on main through the approved merge
   process, and configure environment reviewer/branch restrictions. Set exact
   source/ref/hash policy and journal write permission only after these controls
   are evidenced. The current workflow is not on main (GET returned404 on
   2026-10-17); this window still has no dispatch tool. An approved registered
   manual UI/API trigger is an explicit remaining dependency, not a hidden push
   execution workaround. Default operation remains offline and enable remains off.
5. Obtain distinct one-use RUN/QUERY permissions and perform the real UK test.
   Preserve Git journal ref/commit SHA, Run/Job, InvokeId, redacted target receipt
   and unchanged protected-state evidence. Invalid active mechanisms remain HOLD.
6. Rollback only a separately approved exact new transport installation: disable
   the enable switch/revoke its policy first; preserve all consumed journal refs
   and target evidence, then quarantine/restore only version-bound new files with
   a recorded baseline. Never clear a consumed attempt, erase a ref to retry,
   unmask old services, roll back canonical epochs or start a second writer.
   Unknown cloud/target state stops rollback planning until bounded reconciliation.

### Consolidated external prerequisites — not implementation PASS
- Repository platform/Owner: authorized registration on main, protected environment
  reviewer/ref rules, exact nonsecret policy anchors, namespace retention/write
  control and an actual manual dispatch operator/tool. This window cannot manage
  environments/Secrets or dispatch; no request to disclose/reset cloud key values.
- Original P2 canonical authority/Owner + original fifth reviewer: current ACTIVE
  writer/task/lease/Fence and genuine custody/endpoint registration evidence.
  If the original mechanism is inactive it must stay inactive pending its own gate.
- Authorized UK preparation operator: real exact filesystem/clock/Python/base64,
  installed source closure/policy/ledger and backup/rollback metadata under a new
  exact preparation permit. No live paths have been provisioned by this work.
- Original fifth reviewer: one concentrated review of these changed paths, full
  artifacts and plan; then separate bounded preparation/RUN/QUERY grants as
  appropriate. No old consumed approval is reused; production/P2 install remains
  an independent HOLD.

### Evidence scope
76 local/Hosted-targeted tests include durable cloud-journal fixtures, no-ID and
post-STS failures, cross-job saved-ID query, stale append, query-permit replay,
credential/event refusal, exact payload encoding, target intent/replay, and real
original pinned runtime loading that rejects absent activation without creating
an ACTIVE descriptor. RPC/Git API success cases use adapters/fixtures, not actual
GitHub journal writes or STS/SWAS. The five original runtime files remain unchanged
and are not additional files in this six-path manifest. Real target execution,
actual environment protections, real trust and actual global writer are pending.
