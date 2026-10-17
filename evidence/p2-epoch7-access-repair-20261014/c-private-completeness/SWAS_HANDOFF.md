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
77 local/Hosted-targeted tests include durable cloud-journal fixtures, no-ID and
post-STS failures, cross-job saved-ID query, stale append, query-permit replay,
credential/event refusal, exact payload encoding, target intent/replay, and real
original pinned runtime loading that rejects absent activation without creating
an ACTIVE descriptor. RPC/Git API success cases use adapters/fixtures, not actual
GitHub journal writes or STS/SWAS. The five original runtime files remain unchanged
and are not additional files in this six-path manifest. Real target execution,
actual environment protections, real trust and actual global writer are pending.

Query claims also include a fresh cryptographic nonce in the journal tree: two concurrent consumers of the same permit cannot generate an identical idempotent ref update and both proceed. A losing append remains HOLD.


## Site preparation kit v1 — exact scripts for review, NOT execution permission

This section carries the standalone script inside the existing six-path writer
scope. CI extracts the fenced block below verbatim to `P2_SITE_ENTRY.py`, parses
it as Python3.6, runs actual isolated filesystem tests against those bytes, and
binds the generated script in `SITE_KIT_MANIFEST.json` and the review TAR.
The existing approved transport and receipt source bytes stay unchanged.
No remote code or shell fragments are accepted as an input.

### Accurate stage boundaries
1. `preflight` is a metadata-only, zero-write Root script. A new exact read-only
   UK permit is still required before calling it through the existing four-host
   channel. It does NOT import original P2 modules, read configuration bodies or
   query canonical writer. Missing writer/trust evidence stays UNKNOWN.
2. Work uses its output to produce a private exact plan: schema=1, attempt,
   baseline=the complete preflight object, source_pins=the two frozen hashes,
   installation_scope=RECEIVER_CODE_ONLY_NO_POLICY_OR_RUNTIME. No placeholder
   baseline may be approved. Store the final plan root:root0400.
3. Owner bootstrap scope, separately authorized: create
   `/etc/xuanjun-p2-site` root:root0700, enroll INSTALL_TRUST.json root:root0400,
   and create `/var/lib/xuanjun-p2-site` root:root0700 plus its pre-provisioned
   `prepare.lock` regular single-link root:root0600 (no credentials). Bootstrap must be delivered
   by the existing protected Owner channel and independently checked. This kit
   does not auto-enroll trust or treat its JSON role strings as real custody.
4. `install --attempt <approved-id> --plan <root-plan> --source-dir <root-sources>`
   requires a fresh exact P2_SITE_ONCE approval anchored by that trust. Source
   directory contains the two frozen files named transport.py and
   p2_swas_receipt_validator.py, both regular single-link Root protected files.
   Destination and REMOTE_POLICY.json must be absent. Existing receiver sites
   are NOT an upgrade path: HOLD and prepare a separate exact diff.
5. Installer creates an exclusive transaction under /var/lib/xuanjun-p2-site,
   stages under /usr/local/libexec/.p2-stage-<attempt>, fsyncs each checkpoint,
   and publishes using Linux renameat2(RENAME_NOREPLACE). No policy, per-run
   target ledger, original runtime, unit, broker, ACTIVE descriptor, lease or
   Fence is installed or modified. No cloud credentials or SWAS calls occur.
6. `inspect --attempt ...` reads checkpoint hashes and target metadata only.
   It never resets a consumed attempt or classifies an absent result as success.
7. `rollback` needs a distinct exact approval and re-enrolled matching Root
   anchor. It only quarantines a complete hash-matching new receiver/stage,
   requires REMOTE_POLICY.json still absent, and restores original destination
   absence. Partial stage, ambiguous objects, interrupted rollback or unknown
   external invocation => preserve and HOLD for separately approved recovery.
   Quarantine/evidence are never deleted. There is no automatic retry.

### Owner anchor / permit contract (no live examples or fake identities)
Root INSTALL_TRUST.json exact keys: schema=1, enabled=true, revoked=false,
reviewer_principal, source_writer_principal (different real subjects),
custody_evidence_sha256, comment_id, comment_body_sha256, operation, attempt,
plan_sha256, script_sha256. Independent provenance is an external prerequisite.
Root file and every parent must be non-symlink, Root-owned and not group/other
writable. The anchor itself is exactly0400.

GitHub PR58 approval body = `P2_SITE_ONCE` + LF + JSON exact keys:
decision=SITE_PREPARATION_APPROVED, operation=install OR rollback, attempt,
hostname=iZd7oeikknn1z21sq6ji6zZ, script_sha256, plan_sha256, integer issued_unix
and expires_unix (<=2h), max_executions=1, canonical_changes_allowed=false,
cloud_calls_allowed=false. Body SHA must match Owner's independently enrolled
anchor. Same GitHub account is only an auxiliary origin check. No approval is
generated by this kit. Every invocation rechecks after lock and before rename.

### All new configurations / permissions requested together
- Repository registration of exact manual workflow/ref, environment
  p2-uk-transport reviewer and allowed refs, self-review/bypass protection,
  protected variables and switch initially OFF: Owner repository administrator.
- Journal namespace refs/heads/p2-transport-journal/* creation/non-force append
  and protected retention; limited real Git API race/readback test: Owner admin.
- An actual approved UI/API dispatch operator: Owner designates; neither this
  window nor the migration window currently exposes dispatch/admin tooling.
- New one-use UK metadata preflight authority plus optional separately scoped
  original authenticated observation: original fifth reviewer; execution via
  authorized four-host channel, not ordinary push.
- The three bootstrap objects above, private source/plan staging, immutable
  receiver install and quarantine rollback: new exact Root preparation grant.
- Genuine independent Owner custody and precise original installed module/
  activation path evidence: Owner channel + dots canonical P2 source records;
  actual Root readback is required, historical assertions do not prove writer.
- Separate later REMOTE_POLICY.json registration, per-attempt target directories,
  real ACTIVE/authenticated unique writer evidence and separate RUN/QUERY grants
  remain outside this receiver-code preparation permission. No unmask/activate
  for a transport test. If original P2 is inactive, keep HOLD.
- Real network/kill/fsync/UNKNOWN recovery tests require their own isolation scope
  and expected retained artifacts; do not inject faults into canonical DB.
- Existing cloud Secrets and RAM role are reused; no key values, new RAM account,
  general Root command capability or increased cloud privilege are requested.

RECEIVER_CODE_PREPARATION_ONLY=TRUE
UK_SITE_EXECUTION=NOT_RUN
TRUE_TRUST_AND_WRITER=UNKNOWN
LIVE_APPROVAL=NOT_ISSUED
P2_INSTALL_AND_RELEASE=HOLD

<!-- BEGIN P2_SITE_ENTRY_V1 -->
```python
"""Bounded UK receiver preparation. Never activates the original P2 runtime."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.request as U

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
DEST = Path('/usr/local/libexec/xuanjun-p2-swas')
CONTROL = Path('/var/lib/xuanjun-p2-site')
TRUST = Path('/etc/xuanjun-p2-site/INSTALL_TRUST.json')
SOURCE_PINS = {
    'transport.py': '447c082af86d4012ee65ab3af7207cda1bb9b2813c23b4793694a19b53586b73',
    'p2_swas_receipt_validator.py': 'f2897ff21fdfa301048d205105c6d964740112ccc85aa03778758b96ceac1575'}
META_PATHS = (Path('/usr/local/libexec'), DEST, Path('/etc/xuanjun-p2-swas'),
    Path('/etc/xuanjun-p2-swas/REMOTE_POLICY.json'),
    Path('/etc/xuanjun-development/dispatcher.json'),
    Path('/etc/xuanjun-development/p2-ledger-server-identity.json'),
    Path('/var/lib/xuanjun-development/activation'),
    Path('/run/xuanjun-development/ledger.sock'))


def need(ok):
    if not ok:
        raise RuntimeError('SITE_HOLD_PRESERVE_NO_RETRY')


def canon(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pairs(items):
    result = {}
    for k, v in items:
        need(k not in result)
        result[k] = v
    return result


def protected(p, directory=False, mode=None):
    p = Path(p)
    need(p.is_absolute())
    for node in (p,) + tuple(p.parents):
        s = node.lstat()
        need(s.st_uid == 0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022)
        need(stat.S_ISDIR(s.st_mode) if node != p or directory else
             stat.S_ISREG(s.st_mode) and s.st_nlink == 1)
        if node == p and mode is not None:
            need(stat.S_IMODE(s.st_mode) == mode)


def read(p, limit=1048576, mode=None):
    protected(p, mode=mode)
    fd = os.open(str(p), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_uid == 0 and not before.st_mode & 0o022 and before.st_size <= limit)
        raw = f.read(limit + 1)
        after = os.fstat(f.fileno())
    need(len(raw) <= limit and (before.st_ino, before.st_size, before.st_mtime_ns) ==
         (after.st_ino, after.st_size, after.st_mtime_ns))
    return raw


def metadata(p):
    # Metadata only; no private configuration, credentials, DB, socket or module import.
    try:
        s = p.lstat()
    except FileNotFoundError:
        return {'present': False}
    return {'present': True, 'device': s.st_dev, 'inode': s.st_ino,
            'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode),
            'type': stat.S_IFMT(s.st_mode)}


def preflight():
    return {'schema': 1, 'hostname': os.uname().nodename,
        'uid': os.geteuid(), 'python': list(sys.version_info[:3]),
        'paths': {str(p): metadata(p) for p in META_PATHS},
        'state': 'METADATA_ONLY_NOT_WRITER_OR_TRUST_VERIFICATION',
        'mutations': 0, 'activation': 'NOT_OBSERVED', 'unique_writer': 'UNKNOWN',
        'private_materials_read': False, 'install_authorized': False}


class NoRedirect(U.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        raise RuntimeError('SITE_REDIRECT_DENIED')


def fetch_comment(number):
    need(type(number) is int and number > 0)
    req = U.Request('https://api.github.com/repos/huhongchuan0422-creator/'
        'Repository-name-xuanjun-ai-control/issues/comments/' + str(number),
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'P2-Site-Prepare'})
    opener = U.build_opener(U.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=15) as response:
        raw = response.read(32769)
    need(len(raw) <= 32768)
    data = json.loads(raw, object_pairs_hook=pairs)
    need(data['id'] == number and data['user']['id'] == 332398908 and
         data['issue_url'].endswith('/issues/58'))
    return data['body'].encode()


def authority(operation, attempt, plan_raw, script_raw):
    # This file MUST be enrolled through a separately approved Owner channel.
    # Format/owner checks are not proof of actual independent custody.
    raw = read(TRUST, 16384, 0o400)
    t = json.loads(raw, object_pairs_hook=pairs)
    need(set(t) == {'schema', 'enabled', 'revoked', 'reviewer_principal',
        'source_writer_principal', 'custody_evidence_sha256', 'comment_id',
        'comment_body_sha256', 'operation', 'attempt', 'plan_sha256', 'script_sha256'})
    need(t['schema'] == 1 and t['enabled'] is True and t['revoked'] is False and
         isinstance(t['reviewer_principal'], str) and t['reviewer_principal'] and
         isinstance(t['source_writer_principal'], str) and t['source_writer_principal'] and
         t['reviewer_principal'] != t['source_writer_principal'] and
         re.fullmatch('[0-9a-f]{64}', t['custody_evidence_sha256']) and
         t['operation'] == operation and t['attempt'] == attempt and
         t['plan_sha256'] == sha(plan_raw) and t['script_sha256'] == sha(script_raw))
    body = fetch_comment(t['comment_id'])
    need(sha(body) == t['comment_body_sha256'] and body.startswith(b'P2_SITE_ONCE\n'))
    p = json.loads(body.split(b'\n', 1)[1], object_pairs_hook=pairs)
    need(set(p) == {'decision', 'operation', 'attempt', 'hostname', 'script_sha256',
        'plan_sha256', 'issued_unix', 'expires_unix', 'max_executions',
        'canonical_changes_allowed', 'cloud_calls_allowed'})
    need(p['decision'] == 'SITE_PREPARATION_APPROVED' and p['operation'] == operation and
         p['attempt'] == attempt and p['hostname'] == HOST and
         p['script_sha256'] == sha(script_raw) and p['plan_sha256'] == sha(plan_raw) and
         type(p['issued_unix']) is int and type(p['expires_unix']) is int and
         0 < p['expires_unix'] - p['issued_unix'] <= 7200 and
         p['issued_unix'] <= time.time() < p['expires_unix'] and
         type(p['max_executions']) is int and p['max_executions'] == 1 and
         p['canonical_changes_allowed'] is False and p['cloud_calls_allowed'] is False)
    need(read(TRUST, 16384, 0o400) == raw)
    return {'comment_id': t['comment_id'], 'body_sha256': sha(body),
            'trust_sha256': sha(raw)}


def sync_dir(p):
    fd = os.open(str(p), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create(p, raw, mode):
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    sync_dir(p.parent)


def rename_new(src, dst):
    # Linux RENAME_NOREPLACE: never silently overwrite even an empty raced directory.
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.renameat2
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    need(fn(-100, os.fsencode(src), -100, os.fsencode(dst), 1) == 0)
    sync_dir(Path(src).parent)
    if Path(src).parent != Path(dst).parent:
        sync_dir(Path(dst).parent)


def verify_code(folder):
    protected(folder, directory=True, mode=0o755)
    need(set(p.name for p in folder.iterdir()) == set(SOURCE_PINS))
    for name, digest in SOURCE_PINS.items():
        need(sha(read(folder / name, mode=0o444)) == digest)


def validate_plan(raw, attempt):
    p = json.loads(raw, object_pairs_hook=pairs)
    need(set(p) == {'schema', 'attempt', 'baseline', 'source_pins', 'installation_scope'})
    need(p['schema'] == 1 and p['attempt'] == attempt and p['source_pins'] == SOURCE_PINS and
         p['installation_scope'] == 'RECEIVER_CODE_ONLY_NO_POLICY_OR_RUNTIME')
    b = p['baseline']
    need(b['schema'] == 1 and b['hostname'] == HOST and b['uid'] == 0 and
         b['python'] == [3, 6, 8] and b['mutations'] == 0 and
         b['paths'][str(DEST)] == {'present': False} and
         b['paths']['/etc/xuanjun-p2-swas/REMOTE_POLICY.json'] == {'present': False})
    need(set(b['paths']) == set(str(n) for n in META_PATHS))
    return p


def prepare(operation, attempt, plan_path, source_dir, script_raw):
    need(operation in ('install', 'rollback') and re.fullmatch('[a-z0-9][a-z0-9-]{7,79}', attempt))
    protected(CONTROL, directory=True, mode=0o700)
    protected(DEST.parent, directory=True)
    plan_raw = read(plan_path, 32768, 0o400)
    plan = validate_plan(plan_raw, attempt)
    import fcntl
    # Parent must be pre-provisioned by the separately authorized Owner bootstrap.
    lock = os.open(str(CONTROL / 'prepare.lock'), os.O_RDWR | os.O_NOFOLLOW)
    try:
        meta = os.fstat(lock)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1
             and stat.S_IMODE(meta.st_mode) == 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        auth = authority(operation, attempt, plan_raw, script_raw)
        need(not os.path.lexists('/etc/xuanjun-p2-swas/REMOTE_POLICY.json'))
        need(read(plan_path, 32768, 0o400) == plan_raw)
        txn = CONTROL / attempt
        stage = DEST.parent / ('.p2-stage-' + attempt)
        parked = DEST.parent / ('.p2-quarantine-' + attempt)
        if operation == 'install':
            # Compare all observed metadata, not just the empty destination.
            need(preflight() == plan['baseline'])
            need(not os.path.lexists(txn) and not os.path.lexists(stage) and
                 not os.path.lexists(parked))
            blobs = {n: read(Path(source_dir) / n) for n in SOURCE_PINS}
            need(all(sha(blobs[n]) == SOURCE_PINS[n] for n in blobs))
            # New exclusive transaction directory consumes this attempt before any stage write.
            txn.mkdir(mode=0o700)
            sync_dir(CONTROL)
            create(txn / 'intent.json', canon({'attempt': attempt, 'plan_sha256': sha(plan_raw),
                'script_sha256': sha(script_raw), 'approval': auth, 'state': 'INSTALL_INTENT'}), 0o600)
            stage.mkdir(mode=0o700)
            sync_dir(stage.parent)
            for name, blob in blobs.items():
                create(stage / name, blob, 0o444)
            os.chmod(str(stage), 0o755)
            sync_dir(stage)
            verify_code(stage)
            create(txn / 'staged.json', canon({'state': 'STAGED'}), 0o600)
            need(authority(operation, attempt, plan_raw, script_raw) == auth)
            need(preflight() == plan['baseline'])
            need(not os.path.lexists(DEST))
            rename_new(stage, DEST)
            verify_code(DEST)
            create(txn / 'installed.json', canon({'state': 'RECEIVER_CODE_INSTALLED',
                'policy_enrolled': False, 'runtime_activated': False}), 0o600)
            return {'state': 'RECEIVER_CODE_INSTALLED', 'attempt': attempt,
                    'runtime_activated': False, 'p2_accepted': False}
        # A new exact rollback approval is required. Never retry an interrupted rollback.
        protected(txn, directory=True, mode=0o700)
        intent = json.loads(read(txn / 'intent.json', 8192, 0o600), object_pairs_hook=pairs)
        need(intent['attempt'] == attempt and intent['plan_sha256'] == sha(plan_raw)
             and intent['script_sha256'] == sha(script_raw))
        need(not os.path.lexists(txn / 'rollback-intent.json') and not os.path.lexists(parked))
        need(not (os.path.lexists(DEST) and os.path.lexists(stage)))
        # Known partial objects only; a partial stage is preserved for separate recovery.
        obj = DEST if os.path.lexists(DEST) else stage
        verify_code(obj)
        create(txn / 'rollback-intent.json', canon({'state': 'ROLLBACK_INTENT',
            'approval': auth, 'source': str(obj), 'plan_sha256': sha(plan_raw)}), 0o600)
        need(authority(operation, attempt, plan_raw, script_raw) == auth)
        rename_new(obj, parked)
        verify_code(parked)
        need(not os.path.lexists(DEST) and not os.path.lexists(stage))
        create(txn / 'rolled-back.json', canon({'state': 'QUARANTINED_ORIGINAL_ABSENCE_RESTORED'}), 0o600)
        return {'state': 'QUARANTINED_ORIGINAL_ABSENCE_RESTORED', 'attempt': attempt,
                'evidence_preserved': True, 'p2_accepted': False}
    finally:
        os.close(lock)


def inspect(attempt):
    need(re.fullmatch('[a-z0-9][a-z0-9-]{7,79}', attempt))
    txn = CONTROL / attempt
    protected(txn, directory=True, mode=0o700)
    known = {'intent.json', 'staged.json', 'installed.json', 'rollback-intent.json', 'rolled-back.json'}
    names = set(p.name for p in txn.iterdir())
    need(names <= known)
    # Hash-only output; do not expose approvals or private Root policy contents.
    hashes = {n: sha(read(txn / n, 8192, 0o600)) for n in sorted(names)}
    return {'state': 'CHECKPOINTS_ONLY_NOT_RECOVERY_APPROVAL', 'attempt': attempt,
        'records': hashes, 'target': metadata(DEST), 'retry_allowed': False,
        'canonical_writer': 'NOT_OBSERVED', 'cloud_state': 'NOT_OBSERVED'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('preflight', 'install', 'inspect', 'rollback'))
    parser.add_argument('--attempt', default='')
    parser.add_argument('--plan', default='')
    parser.add_argument('--source-dir', default='')
    a = parser.parse_args()
    need(os.getuid() == os.geteuid() == 0 and os.uname().nodename == HOST)
    os.umask(0o022)
    if a.action == 'preflight':
        result = preflight()
    elif a.action == 'inspect':
        result = inspect(a.attempt)
    else:
        script_raw = read(Path(__file__).absolute())
        result = prepare(a.action, a.attempt, a.plan, a.source_dir, script_raw)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"state":"HOLD","retry_allowed":false,"preserve_evidence":true}', flush=True)
        raise SystemExit(2) from None
```
<!-- END P2_SITE_ENTRY_V1 -->
