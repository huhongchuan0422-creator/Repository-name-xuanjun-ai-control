# PR #122 fixed read-only admission probe: disabled local candidate

Prepared 2026-10-17 UTC. **ROOT_ACCOUNT_CREATION_HOLD remains unchanged.** This package is a local review deliverable, not execution admission, publication, a registered workflow, or target evidence. No GitHub write, cloud request, live host probe, account mutation, receipt reservation, or new credentials occurred while preparing it.

## Preserved authority and approved source

The owner’s existing authorization for the fixed `xuanjun-customer` service account remains intact. Do not request broad account-creation authorization again. The reported formal Task5 #6231037637 decision at `6846d29ca58c9e8a4aac75f8e15269dda89d246b` was an offline source approval. The narrower fresh root probe and final execution/registration admission remain separate pending gates.

`approved_account_prepare.py` is byte-for-byte the approved standalone source: 16,959 bytes, SHA-256 `885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818`. Neither that original source nor the existing transport was edited. The existing transport hash remains `c0db7caa615abee1b5cc2db973ea889a507f1317a3edc411bfee873e7da27e2f`.

The caller loads the exact hash-checked source with `__name__=approved_account_payload_readonly`; it never calls its main, create_once, run_fixed_useradd, private_postcheck, reserve_original_evidence, or record_original_evidence. Approved method definitions remain in those unchanged bytes but are not invoked by the probe. Existing Python/temporary-venv metadata evidence is reused; no installation, rebuild, or repeat platform setup occurred.

## Fixed observation scope

Only Shanghai `cn-shanghai`, instance `3a22c458934142eea89ec6e3bf481a57`, hostname `iZvt5t8tlrm8oiZ`, real and effective UID 0. The unchanged OS constructor verifies host/root. It opens the existing canonical `/var/lib/xuanjun-customer-channel/channel.py` read-only/no-follow, validates the original parent-chain and inode contract, and acquires its existing exclusive nonblocking flock. It creates no lock file or host receipt.

Under that lock the caller:

1. Uses approved collect_fixture and plan solely for named account/group absence and fixed path metadata. No NSS record, password field, or global account/group enumeration is exported. Exceptions become UNKNOWN, not absent.
2. Calls approved platform_preconditions: fixed `useradd --help`, fixed public `/etc/login.defs` and `/etc/default/useradd`, metadata/emptiness checks of the three fixed hook directories, and secure metadata validation of passwd/sudo. It never invokes passwd, sudo, useradd mutation, or hooks.
3. Exports supported required flag booleans, hook/default booleans, positive system UID/GID ranges and their ordering. On any platform exception all platform results become UNKNOWN, without exception text.
4. Reports metadata and SHA-256 identity of the four fixed useradd/nologin/passwd/sudo binaries and canonical channel.py. Hash reads are bounded to 16 MiB, no-follow, regular-file only, with inode/name and before/after size/mtime/ctime checks. Binary contents never leave the process.
5. If root-protected `/usr/bin/rpm` passes the approved secure executable check, executes only two fixed `rpm -qf --qf ... /usr/sbin/useradd` reads. It records owner package name, version, release, architecture, SHA-256 algorithm and useradd’s RPM-recorded digest, then compares that digest with the observed binary. A bounded captured filename/digest array is necessary to select useradd; unrelated entries are discarded, never exported. RPM absent, unsafe, malformed, duplicate ownership, a non-SHA256 record, or query failure gives UNKNOWN. No installation or package changes.
6. Checks only existence/metadata of the original account receipt. It does not read, reserve, mkdir, delete, repair, or write that receipt. Existing/unknown receipt remains account-creation HOLD.
7. Repeats approved absence observations under the same lock, reports snapshot stability and named lock inode stability, and releases the lock.

No protected application configuration is read. The new caller has no generic root-command, path, username, or CLI input. The only external tool executions reachable from the probe are useradd --help and the two fixed RPM queries.

### Evidence versus inference

The approved adapter hardcodes `mail_spool_suppressed` and `no_subid_allocation` from documented shadow semantics. The caller deliberately does **not** export those as observed true. It reports `INFERRED_DOCUMENTED_SYSTEM_ACCOUNT_NO_F_NOT_EXPERIMENTALLY_TESTED` only when the observed owner package is shadow-utils, its SHA-256 file record matches actual useradd bytes, and the required flags were observed. Otherwise semantics remain UNKNOWN.

This inference uses the previously reviewed [shadow useradd documentation](https://github.com/shadow-maint/shadow/blob/master/man/useradd.8.xml) for system-account subordinate-ID behavior without `-F`, and [useradd source](https://raw.githubusercontent.com/shadow-maint/shadow/master/src/useradd.c) for system-account mail suppression. These are prior references, not newly fetched or immutable target-version source attestations. Observed version and file consistency enable the reviewer to evaluate this contract without another broad audit; vendor divergence is not experimentally excluded. The report distinguishes exact package/digest observations from documented behavior inference.

An available advisory lock demonstrates only momentary exclusion of cooperating channel writers. It never establishes global root-writer exclusion. That field remains UNKNOWN. A separate probe also never replaces the immediate checks in an eventual approved creation transaction.

## Disabled transport and exact future trigger

`readonly_transport.py` and `readonly-transport-candidate.yml` are new, separate, disabled candidates. Six old helpers (need, persist, github, gate, quote, rpc) are copied verbatim and tested for equality. The mutation command, validator and main are not reused. The transport compresses a fixed JSON envelope containing exact approved source and the separate caller; hashes bind both. No external source fetch or arbitrary command input is accepted.

All disarm controls remain:
- Workflow literal `false`.
- `ARMED = False`.
- `EXECUTION_ADMISSION = False`.
- Expiry `1970-01-01T00:00:00+00:00`.
- Fixed executable workflow ref is this repository’s exact workflow path at `refs/pull/122/merge`. Runtime `GITHUB_WORKFLOW_SHA` must equal the fresh PR `merge_commit_sha`, with the current full head SHA and event base SHA unchanged. No self-referential commit constant is embedded.

Proposed registration is only on PR #122’s actual head branch `feature/stage5-next25-integration-20261015`, retaining its Draft state and existing base. Proposed path: `.github/workflows/aliyun-account-readonly-admission-once-20261017.yml`. Sole proposed manual protected-owner label:

`xj-ro-<resulting-full-current-PR122-head-SHA>`

The `xj-ro-` prefix plus 40-character full head SHA is 46 characters. Only pull_request:labeled, owner actor and triggering actor, matching sender, attempt 1, exact current PR/head/base, workflow path, label and history are accepted. No push, dispatch, pull_request_target or ready-for-review trigger. Do not emit a label while disarmed; matching skipped/failed/cancelled attempts consume the existing one-shot history contract. Actual head and executable workflow identity require fresh read-only verification at registration; the parent’s earlier `ffebd6254c0116ae8023efcc2ae714fc5a275560` observation is historical, not a current claim. GitHub executable workflow-ref/merge semantics must be resolved rather than inferred from a label. After registration, external Task5 admission must independently record and verify final head SHA, merge SHA and workflow blob SHA before the label is emitted. The label is an execution trigger, never evidence of independent review. `EXECUTION_ADMISSION` stays false until that distinct exact-byte admission exists; no new persistent variable or credential is introduced.

Existing STS AssumeRole and fixed SWAS transport only. Runtime verifies the returned assumed-role ARN against account `1384884686754410`, role `xuanjun-automation` and exact generated session name; no secrets are printed. The sanitized runner evidence binds role ARN, session ARN, head, label, run ID, executable ref/SHA, envelope/caller hash, nonce, expiry, intent and InvokeId. This is an ordinary run evidence artifact, not a second host receipt or authorization ledger. Existing canonical host receipt stays untouched. Unknown dispatch response, missing InvokeId, malformed result, or polling failure means HOLD, never redispatch. Reconcile only the known invocation if separately authorized.

Probe completion is `READONLY_OBSERVED`, never an account-creation PASS. Root result fields for STS and registered trigger are UNKNOWN because the host cannot attest GitHub/STS; separate runner evidence supplies those facts. The existing evidence index remains the place to bind all run artifacts; this package does not create a replacement index or application framework.

## Narrow missing admission and review outcome

A future decision may admit only these exact fixed root read-only bytes through the existing role/target channel, the exact final executable workflow ref/SHA, fixed manual label, attempt 1 and short expiry. It must separately authorize necessary registration publication/trigger if not already covered. Retain existing owner account authorization; ask only for the missing bounded root-probe/registration action. No new credentials, IAM expansion, security settings, generic root channel or other hosts are included.

The result needed is fresh named account/group/path/receipt absence, actual tool hashes and flags/defaults/hooks/ranges, package/file consistency and clearly labeled semantics inference, canonical lock observation, current STS identity and exact registered trigger evidence. A missing mandatory fact remains HOLD. Any admitted creation still uses the original approved account transaction and receipt, not this probe; no automatic transition to creation exists here.

## Local verification and files

20 offline unittest cases passed. They cover exact approved bytes and hash rejection; inert load; zero mutation calls; schema and nested-secret rejection; NSS errors/row sanitization; platform error sanitization and the actual approved platform helper limited to mocked useradd --help; disabled no-network behavior; helper equality; immutable bundle/hash and command size; fixed RPC action allowlist; every disarm gate; short-label/full-SHA binding; runtime merge/ref/head/base drift rejection; response identity binding; bounded RPM selection/failure; caller AST forbidden-call scan; output size.

Transport command is 11,281 UTF-8 bytes; base64 length 15,044, below the inherited 16,384-byte limit. All tests are offline with injected fixtures/mocks. They do not attest the real host, root access, credentials, workflow registration, RPM availability or target preconditions.

- `approved_account_prepare.py`: unchanged approved bytes.
- `readonly_probe.py`: new bounded caller.
- `readonly_transport.py`: generated disabled transport.
- `readonly-transport-candidate.yml`: generated disabled workflow candidate.
- `transport_delta.py.txt`: source of changed transport functions.
- `build_candidate.py`: deterministic local-only packager.
- `bundle.json`: exact source envelope (not executed).
- `tests/test_probe.py`, `TEST_RESULTS.log`: offline checks and results.
- `FILE_HASHES.json`: local artifact integrity manifest, not a transaction ledger.

For reproducibility: run `PYTHONDONTWRITEBYTECODE=1 python3 build_candidate.py`, then `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` from this directory. Do not run readonly_transport.py, the workflow, or the approved payload against a live host during review.
