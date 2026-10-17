# Disabled account-only transport candidate

Prepared locally only. No GitHub file was created or changed, no workflow was triggered, no secrets were read, and no host command or payload was executed.

## Review artifact and intended destination

- Local artifact: `transport-candidate.yml`.
- Sole intended new repository path: `.github/workflows/aliyun-account-prepare-once-20261017.yml`.
- Repository: `huhongchuan0422-creator/Repository-name-xuanjun-ai-control`.
- Original PR #122 head branch: `feature/stage5-next25-integration-20261015`; observed pre-publication head supplied by parent: `ffebd6254c0116ae8023efcc2ae714fc5a275560`.
- Base: `feature/stage5-merchant-platform-storefront-ui-20261014`.
- Do not attach this workflow to a website/work branch or another PR, and do not modify existing repository files.
- Embedded exact payload SHA-256: `885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818`.
- Payload review is independent. This file is not evidence that execution, publication, or arming has been approved.

## Explicit disarmed state

The job expression starts with literal `false`, Python `ARMED` is `False`, and the expiry is already past (`1970-01-01`). All three must be deliberately reviewed and updated only after approval; preparation does not enable them. A future expiry must be at most 30 minutes ahead when the job starts and still valid immediately before RunCommand. Publication changes the head SHA: the sole label must use the actual resulting event head SHA, never the pre-publication head above.

Only `pull_request: labeled` is registered. No `push`, dispatch, pull_request_target, arbitrary checkout, mutable external payload fetch, or broad root dispatcher is present. The exact label is `xuanjun-account-prepare-once-20261017-` plus the full event head SHA. The fixed actor and triggering actor must both be `huhongchuan0422-creator`. PR number, same-repository source, branch, base, open state (Draft is preserved), live unchanged SHA, label presence, known mergeability (no ready-for-review or clean-state requirement), run path and attempt are checked. The literal job gate also prevents secrets reaching unrelated runs.

## One-shot and transport

Concurrency serializes the fixed operation and never cancels an in-flight run. Under that gate, the workflow reads its own durable GitHub run history with complete pagination and blocks any other same-workflow run with either the same head SHA or same label/display title, including cancelled, failed, and skipped runs. This is intentionally stricter than allowing a retry after a preflight failure. History API errors, truncation, schema uncertainty, incomplete history, or re-runs fail closed. Never delete run history or change the operation identity to bypass this guard. GitHub administrator deletion of history is outside this guard; the remote receipt is an independent final barrier against duplicate account creation.

The operation uses only the existing `ALIYUN_ACCESS_KEY_ID` and `ALIYUN_ACCESS_KEY_SECRET` runtime secret references and existing role `acs:ram::1384884686754410:role/xuanjun-automation`, with the established STS session flow. No new IAM grant, stored credential, key, or persistent access is requested. Allowed RPC triples are fixed to STS AssumeRole and Shanghai SWAS RunCommand/DescribeInvocationResult. The sole target is `cn-shanghai`, instance `3a22c458934142eea89ec6e3bf481a57`, hostname `iZvt5t8tlrm8oiZ`. There is exactly one RunCommand call site and no automatic dispatch retry. No older command batches or private keys are reused.

The RPC signing design was inspected from the existing migration workflow `.github/workflows/aliyun-four-host-readonly.yml` at commit `18f8fd8aae7a3af90263b8ef10414663c0a6b14e`, blob `b7539c1149c4e01e495e40824df6ca38b4efb3f5`. The new transport narrows endpoint/action allowlisting and suppresses API bodies, URLs, credentials and exceptions.

Before RunCommand, fixed nonsecret INTENT is written, flushed and fsynced and printed with flush. A valid returned InvokeId is immediately printed with flush and then stored and fsynced before any poll. The always-run artifact step preserves only this receipt, using a pinned upload-artifact revision. Abrupt runner destruction may prevent artifact upload; GitHub run history and the flushed log remain the pre-dispatch evidence. A missing/malformed response is HOLD with no automatic RunCommand retry, even when the remote result is unknown.

The remote command verifies the payload byte hash, expected host, real and effective root before calling its fixed account-only main function. The embedded payload uses its existing canonical `channel.py` lock and exclusive account-preparation receipt. The transport creates no additional remote ledger. No service deployment, application change, root authorization expansion, account repair, deletion or credential installation is included.

Polling is bounded to 180 seconds, with 20-second request timeouts. Any unknown query outcome ends HOLD and does not redispatch. Every queried result must identify the expected instance and InvokeId. Success additionally requires terminal Success, integer exit code zero, exact bounded JSON schema, fixed hostname, nonce and payload hash, verified account result and bounded positive UID/GID. Only allowlisted account metadata is persisted; raw remote output, shadow data, API response bodies and credentials are never output. The remote result explicitly does not claim a global polkit policy audit.

## Static verification completed

- YAML parsed successfully (PyYAML's YAML 1.1 parser represents the `on` key as boolean true; its parsed trigger content was explicitly checked).
- Embedded bash passed `bash -n`.
- Inline Python passed AST parsing and compilation without execution.
- Embedded payload passed AST parsing, decompression and exact byte/hash equality against the final local payload.
- No transport, payload, cloud API mutation or host operation was executed.

The candidate still needs independent transport review, approval, current PR/head verification, a verified action pin if required by repository policy, and the final short expiry before any future publication or arming. If any payload byte changes, regenerate the embedded payload and hash and repeat review rather than accepting a stale hash.

## Review corrections

Draft PR state is permitted and never changed. History rejects matching runs regardless numeric ID because concurrency is not FIFO. The remote wrapper uses zlib-compressed embedded source and verifies the decompressed byte hash. Before dispatch, encoded command length must be at most 16,384 bytes, following the [official SWAS RunCommand limit](https://www.alibabacloud.com/help/en/simple-application-server/developer-reference/api-swas-open-2020-06-01-runcommand).

Offline tests: `tests/test_transport_candidate.py` loads only AST-selected declarations and literal constants from the actual YAML. All event, GitHub HTTP, cloud RPC, receipt and output interactions are mocked; the generated remote command is parsed only. 32 tests pass covering disabled/expiry, Draft and new head acceptance, actor/fork/head drift, older/newer duplicates, incomplete/API-error history, payload hash, unknown dispatch no-retry, pre-dispatch/pre-poll receipt ordering, bounded polling, identity/schema checks, endpoint/error rejection and compressed command size. Both HTTP clients explicitly disable proxy environment inheritance and redirects. No real secrets or network are used by these tests.
