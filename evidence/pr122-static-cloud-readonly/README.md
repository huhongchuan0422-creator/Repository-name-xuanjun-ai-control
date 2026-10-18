# PR122 fixed domestic staging observation candidate

Local candidate only. No workflow was published or triggered, no cloud API or
host command was executed, and no installation or deployment was attempted.

## Two-branch repository layout for the existing PR122 writer

- Source branch: `feature/work-pr122-site-hub-integration-20261016`. Place Python
  files, this README, and both YAML files under
  `evidence/pr122-static-cloud-readonly/`. The full
  `pr122-staging-readonly.yml` here is an inert reviewed template.
- On that source branch only, publish `pr122-staging-readonly-source-tests.yml`
  as `.github/workflows/pr122-staging-readonly.yml`. It has pure push-triggered
  hosted mock tests only, no cloud step, secret reference or PR label handler.
- After the source branch CAS, mechanically replace the four occurrences of
  `__READONLY_SOURCE_HEAD_40_HEX__` in the inert full template with the exact
  source commit. On actual PR122 branch
  `feature/stage5-next25-integration-20261015`, add only the substituted
  `.github/workflows/pr122-staging-readonly.yml`. Every checkout and the runtime
  environment contain that same complete literal source SHA. No dynamic source
  input or partial ref is accepted. Do not copy product or helper files there.
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
PR122, branch `feature/stage5-next25-integration-20261015`, with an exact
full-40-character label `pr122-staging-readonly-<current HEAD>`. The event head,
live PR head, current workflow run identity, actor IDs, repository IDs, and
branch must all agree. No fixed stale HEAD is embedded. Ordinary push/PR events
run hosted tests only. Reruns cannot dispatch.

Only the minimal workflow is added to the actual PR122 branch, whose observed
pre-adapter HEAD was `3beb5db669ec0004a4d3ef278f5519e0100e4403`. Its new commit is
PR_EVENT_HEAD, not the checkout/source HEAD. The draft PR's observed base is
`feature/stage5-merchant-platform-storefront-ui-20261014`. This does not merge,
execute or supersede the separately reviewed website product on the historical
work branch at `73454b6f973e073067de7afb7580c1ac709ede2f`.

The runtime separately binds READONLY_SOURCE_HEAD to the work-branch GitHub ref
and local clean git HEAD. It also checks that the actual workflow file fetched
at PR_EVENT_HEAD equals the source template with only the four source placeholders
substituted. Thus an arbitrary environment value cannot select new source. Both
heads are persisted in intent/dispatch/result, embedded in the fixed command,
and verified in the remote output and any query-only recovery. Keep the source
branch fixed until the invocation reaches a verified terminal result; later
source-branch drift causes HOLD, including for query-only.

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
   InvokeId to the domestic instance, both original heads and command hash. It can only
   DescribeInvocationResult; it never calls RunCommand. No arbitrary InvokeId
   is accepted. A query after either bound HEAD changes is intentionally not supported
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
16KiB budget. The exact measured command sizes are recorded in the candidate
manifest. This is a local size check, not a live SWAS compatibility claim.

## Local validation and limits

Run `python3 -m unittest discover -s evidence/pr122-static-cloud-readonly -p
'test_*.py' -v` after mapping files into the repository. No tests contact GitHub,
Aliyun, or hosts; socket creation is rejected in every test. The source command
is compiled but never executed locally. Current 44 runner tests cover real-shape
SKIPPED timestamps, duplicate rerun jobs, pagination gaps, actor/head restrictions,
artifact digest/readback/redirect controls, lost InvokeId, strict query bindings,
output privacy, HOLD handling, and command size. Helper fixture tests are separate.

Independent review, exact publication into PR122, hosted tests on that new HEAD,
and explicit label admission remain outside this local candidate work. Even a
successful observation would not transfer missing inputs, install the website,
prove current staging paths exist, or grant production admission.
