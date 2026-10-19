# P2 resumable installation rewrite

Owner requested reuse of completed work and replacement of the host-coupled installation layer on 2026-10-20 (Asia/Shanghai).

Base: ad87e5b933f6daf70b574c6459bfb2b99898a755. Existing code, evidence and production storage remain intact. This branch does not deploy or grant production permission.

## Inheritance

Retain the existing AuthorityStore and Grant quota, signature verification, protected receipt transport, registry binding and reconciliation implementations. They still require explicit integration; this journal does not replace their authority. Historical lifecycle Plan/seed compatibility is evidence for its paired Kit only, not approval for the rewritten release.

## Implemented

`journal.py` provides a private SQLite/WAL installation metadata store, exclusive session lock, exact Plan/release binding, durable RUNNING events, predecessor readback checks, verified commits and explicit no-effect reconciliation. Completed batches cannot be reinstalled. A crash preserves RUNNING and blocks blind retries. Changing a Plan cannot reset its journal. Earlier committed evidence is never overwritten by a later failed batch.

All effect and no-effect verifiers are adapter interfaces, not authorization or evidence by themselves. Production must supply authenticated readback. This module issues no root commands, creates no services, consumes no Grant, and accesses no production database. It does not yet implement a complete installer or rollback engine.

## Runtime contract before implementation

The replacement should run its application processes inside a container without requiring host systemd. Explicitly enumerate the retained original functions and map each to a real container implementation or an external host prerequisite. Network-none Docker can validate offline components; it cannot demonstrate external task intake or cloud execution. Do not claim unchanged full functionality before this mapping is complete.

The proposed seven batches remain a design draft. Do not mechanically divide the original sixteen-stage coordinator or adopt its host snapshot as a new container Plan. Define the new Plan, immutable resource ownership and rollback boundaries before connecting effectful operations. Host service control and cgroup administration remain separate prerequisites where required.

## Next implementation gates

1. Complete original-function/runtime dependency mapping and freeze executable batch boundaries.
2. Connect existing Grant/AuthorityStore authority to each batch, preserving aggregate attempt limits and unknown-transaction holds.
3. Implement real artifact staging and readback first, then isolated container process/service adapters and per-batch recovery.
4. Demonstrate forced process death and restart, retained DB/WAL and earlier batch preservation with real filesystem effects.
5. Integrate exact release/Plan signatures, protected entry and registry before any production activation.

Validation: seven local regression cases passed for failure retention across reopen, unknown-effect hold, predecessor drift, ordering/idempotence, Plan changes, concurrent sessions and unverified receipt rejection. These are metadata integration checks, not sixteen-stage installation acceptance.
