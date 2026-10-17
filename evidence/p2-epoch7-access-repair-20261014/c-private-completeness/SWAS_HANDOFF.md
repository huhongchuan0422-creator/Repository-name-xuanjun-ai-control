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
