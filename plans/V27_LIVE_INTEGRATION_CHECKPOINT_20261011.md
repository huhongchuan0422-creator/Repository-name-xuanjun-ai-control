# V2.7 UK development integration checkpoint

Authority: Owner's re-uploaded V2.7 architecture document on 2026-10-11,
SHA256 `5200a302c89bd26086393a914681c564b6ac370885f300ada7f2ba49b358ba87`.
Sections 12 and 14 retain the existing stage/node sequence. No new task registry
or early GEO development is authorized by this checkpoint.

## Observed UK and Tokyo evidence

UK Actions run 38112254844, commit
`2b4de3ce4e49b5c9c297c953e00bd5a019d08fc1`, ran 133 tests successfully on
the actual UK Python 3.6 host. The authorized read-only root gateway exported
actual source contracts and schemas after Owner corrected the export directory.

- Existing UK OpenClaw, Coordinator and Owner callback services are active.
- Model configuration: `openai/gpt-6.1-sol`; fallback count: 0.
- Existing UK-to-Tokyo SSH identity executed the fixed read-only source audit.
- Codex binaries were absent from the four inspected conventional paths, and
  `/home/xuanjun_dev/.codex/auth.json` was absent. Other installation or auth
  locations and OpenClaw subscription access remain unverified.
- Existing task, approval, event, callback request/replay and notification outbox
  schemas are present. Execution ledger side tables are not yet activated.

UK Coordinator source hash:
`70e0d03412f7729f396652df041930f689a6ea674e4e33bf370da1e40a90f9c7`.
UK callback source hash:
`351fd227e18304d44b8d95cf6727685ba08b828ea2cb60a71fa1947855b9bf0e`.

## Reused components and increments

Reuse the existing SQLite task authority, callback authority, Telegram webhook,
notification outbox, private GitHub repository and dedicated UK Runner.
Add fenced execution metadata, bounded persistent dispatch, a Developer/independent
QA pipeline and an authenticated read-only Owner workbench. Local test evidence
does not imply a deployed service or actual model inference.

Independent QA added regression coverage for unpersisted completion/checkpoints,
expired leases, preservation of side-effect evidence, bounded failed dispatch,
invalid checkpoint phases, sensitive checkpoint isolation and real two-thread
nonblocking dispatch. The resulting local suite passes 142 tests.

## Activation dependencies and human queue

1. Verify the existing OpenClaw authentication source and an actual authorized
   Sol model response. Subscription quota and API usage remain distinct;
   unsupported quota telemetry stays UNKNOWN. Never switch models on failure.
2. Install the read-only Owner workbench as a persistent service and verify
   authenticated access. Public TLS routing remains a separate verified step.
3. Provide per-job cgroup/process containment and isolated development credentials.
4. Activate the new dispatcher through a controlled service change. The old
   Coordinator claims unknown kinds; do not insert CODEX_EXEC while it controls
   dispatch, or it could falsely mark those tasks DONE.
5. Verify authenticated Owner reply routing against the existing live callback,
   approve/reject end-to-end, and continued normal customer handling.
6. Run two real development tasks, exact-commit CI, independent QA, checkpoint
   resume, and next-node advance before claiming autonomous-loop PASS.

Domestic and Korea long-term SSH/tunnel availability is NOT_VERIFIED. Inspect
existing units and identities first; extend persistent services only for actual
missing connections. No trading authority expansion is part of this work.

Current production integration status: PARTIAL. The draft PR is reviewable code,
not evidence that the dashboard or development loop is online.
