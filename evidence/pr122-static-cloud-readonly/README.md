# PR122 fixed domestic staging observation candidate

Local candidate only. No workflow was published or triggered, no cloud API or
host command was executed, and no installation or deployment was attempted.

## Repository layout for the existing PR122 writer

- Place `pr122-staging-readonly.yml` at
  `.github/workflows/pr122-staging-readonly.yml`.
- Place the Python files, this README, and a copy of that workflow at
  `evidence/pr122-static-cloud-readonly/`. The second workflow copy is inert and
  is used by the mock workflow-contract test.
- The independent helper's readable source and its 27 fixture tests may also be
  placed in this directory; the runner actually executes only `HELPER_BYTES`
  frozen in `frozen_helper.py`, with its SHA checked before dispatch and on host.
- No PR99 file or existing server attempt directory is changed by this candidate.

## Exact scope and admission

Only `DOMESTIC_STAGING_READONLY`, cn-shanghai, instance
`3a22c458934142eea89ec6e3bf481a57`, hostname `iZvt5t8tlrm8oiZ`, root,
and the existing role `acs:ram::1384884686754410:role/xuanjun-automation`.
The fixed interpreter is `/usr/bin/python3.11`, as used by the prior successful
S07/S09 domestic SWAS commands. Its availability is inherited historical evidence,
not re-observed by this local work.

The only cloud entry is an Owner 332398908 label event in repository 1413132159,
PR122, branch `feature/work-pr122-site-hub-integration-20261016`, with an exact
full-40-character label `pr122-staging-readonly-<current HEAD>`. The event head,
live PR head, current workflow run identity, actor IDs, repository IDs, and
branch must all agree. No fixed stale HEAD is embedded. Ordinary push/PR events
run hosted tests only. Reruns cannot dispatch.

The frozen helper is 8003 bytes, SHA256
`14126e5c4da00dea5b6ac300515ac4ae921c0c14b08b4128a195d4597728df3b`.
Its fixed eight historical paths produce only label, state, bounded size and
SHA256. It does not read file contents into logs/artifacts. A HOLD stops all
remaining reads; later items are `NOT_READ`. `collect()` itself installs the
20-second SIGALRM and restores the old handler. The wrapper adds nonce/head/SHA,
hostname/root binding and suppresses all uncaught exceptions to a fixed message.

## At-most-once and query behavior

1. Workflow-level concurrency serializes the complete action family per HEAD,
   with cancel-in-progress false.
2. Every dispatch checks all workflow runs (bounded complete pagination, no time
   cutoff) and requires a contiguous run_number sequence starting at 1. Missing,
   deleted, truncated, inconsistent or inaccessible history causes HOLD.
3. For that exact HEAD, a prior cloud job is exempt only when it is explicitly
   completed/skipped with zero steps. GitHub gives skipped jobs a started_at,
   so the timestamp alone is not used. Queued/running/cancelled/ambiguous jobs
   consume the HEAD conservatively; filter=all includes rerun job attempts.
4. The canonical intent is uploaded as an immutable artifact before STS.
   Immediately before dispatch the runner repeats live/history admission and
   reads back the exact artifact ID, checks ZIP SHA256, member and canonical
   content. Missing digest, expired artifact or readback failure causes HOLD.
5. The fixed signer makes RunCommand at most once. The local InvokeId record is
   fsynced and uploaded before query. A missing/invalid/lost InvokeId is UNKNOWN,
   never recovered by issuing another command. The consumed run blocks replay
   even if the runner dies before uploading the dispatch record.
6. `pr122-staging-readonly-query-<same current HEAD>` selects the unique prior
   consumed run and verifies its original intent + dispatch artifacts. It binds
   InvokeId to the domestic instance and original command hash. It can only
   DescribeInvocationResult; it never calls RunCommand. No arbitrary InvokeId
   is accepted. A query after source HEAD changes is intentionally not supported
   by this candidate and must remain HOLD until an exact reviewed recovery path
   exists. Query observation timeout is PENDING/HOLD, not proof of completion.

GitHub artifact download permits one verified HTTPS redirect to the fixed
allowed Azure/actions storage suffixes, without forwarding Authorization.
A second redirect is rejected. Unknown provider endpoint/digest/metadata shapes
are HOLD, not an excuse to weaken validation.

## Source and privacy

`original_rpc.py` copies the original `Hold`, `safe`, `quote`, `NoRedirect` and
`rpc` definitions verbatim from `ORIGINAL_SWAS_WORKFLOW.yml` SHA256
`872e00a3586863c88dd233a9ba72506adaca9302d8acb3011948f22d45a723da`, with
the HOSTS endpoint allowlist restricted to domestic. The runtime wrapper exposes
only fixed AssumeRole / RunCommand / DescribeInvocationResult operations. It
does not print raw API exception text or unvalidated remote output. Existing
repository secret names are referenced only in the cloud dispatch/query steps.
There is no new account, credential storage, OSS bucket, permission grant or
credential export.

The original working RPC uses raw CommandContent. This candidate retains that
protocol and additionally checks the command's base64 representation against the
16KiB budget. With example 40-char HEAD/64-char nonce: 4864 raw bytes / 6488 base64
bytes. This is a local size check, not a live SWAS compatibility claim.

## Local validation and limits

Run `python3 -m unittest discover -s evidence/pr122-static-cloud-readonly -p
'test_*.py' -v` after mapping files into the repository. No tests contact GitHub,
Aliyun, or hosts; socket creation is rejected in every test. The source command
is compiled but never executed locally. Current 36 runner tests cover real-shape
SKIPPED timestamps, duplicate rerun jobs, pagination gaps, actor/head restrictions,
artifact digest/readback/redirect controls, lost InvokeId, strict query bindings,
output privacy, HOLD handling, and command size. Helper fixture tests are separate.

Independent review, exact publication into PR122, hosted tests on that new HEAD,
and explicit label admission remain outside this local candidate work. Even a
successful observation would not transfer missing inputs, install the website,
prove current staging paths exist, or grant production admission.
