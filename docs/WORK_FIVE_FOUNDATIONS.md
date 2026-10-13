# Five Work foundation scopes — source preparation

Registered on PR17 comment6136289637 under the same canonical parent.
Source owner is WORK_NATIVE. Owner later clarified: Work retains responsibility
for all seven scopes until Owner explicitly requests transfer. Publishing a PR
or stopping local writes is not a handoff. No successor or runtime lease claimed.

These utilities project caller-authenticated evidence from existing authorities;
they do not create a registry, queue, database, scheduler, approval system or
provider. Source development is ready; production integration depends on P2 and
Stage1 admission and the existing Tokyo/Domestic asset-reuse check. No host scan
or migration is claimed. Tests use fixtures; they do not prove live gates.

| Scope | Function | Input and caller obligation | Output meaning |
| --- | --- | --- | --- |
| 1.9 dependencies | dependency_view(target, nodes) | Complete canonical DAG; exact dependency acceptance evidence; source authentication and current policy | DEPENDENCIES_EVIDENCED describes ancestor records only, never admission |
| 1.10 resume | resume_view(evidence, now, max_age=300) | Existing controller's version-bound, fresh proof of all eight conditions | PREREQUISITES_REPORTED never resumes a worker |
| 1.12 alert | alert_payload(task_id, reason, deadline, workspace_origin) | Existing verified Owner workspace origin, enrolled recipient and task authorization | Minimal Chinese text plus login-protected task-view URL, never send/approve |
| 1.13 usage | usage_projection(samples) | One cumulative final/consistent sample per run, complete canonical run inventory and evidence | Supplied counter sum only, no quota balance or monetary amount |
| 1.15 handoff | handoff_view(expected, observed) | Existing canonical controller's current task/spec/checkpoint/commit/artifact binding and stop/ACK/lease evidence | HANDOFF_PROOFS_REPORTED never transfers execution authority |

## Exact source schemas

Dependency nodes are a mapping from identifiers to objects with exactly
dependencies (unique list), state, evidence_sha256. Ancestors need ACCEPTED and
a valid SHA256; target acceptance is not required to inspect its prerequisites.
Missing/malformed ancestors, cycles and missing evidence HOLD. At most1000 nodes
and100 edges per node; iterative traversal avoids Python recursion limits.

Resume input has exactly observed_at, binding_sha256 and literal-boolean fields
identity_current, checkpoint_verified, old_writer_stopped, old_fence_revoked,
effects_reconciled, dependencies_accepted, budget_available, owner_authorized.
Missing, false or unknown values HOLD. These booleans are reports, not verified
facts: caller verifies their evidence at the current canonical admission boundary.
Freshness max_age is1..3600 seconds; default300. Atomic live recheck remains required.

Alert reason is one of VERIFICATION/RESOURCE/SECURITY/HANDOFF/DELIVERY. Task IDs
are bounded ASCII IDs; deadlines are nonnegative Unix seconds. Origin is HTTPS,
with optional valid port, no credentials/path/query/fragment. Origin validation
does not authenticate a hostname; caller must obtain the existing reviewed origin
from protected configuration. Generated path /owner/tasks/{id} must be mapped by
the existing authenticated workspace before activation. No generic URLs, freeform
reason/log/secret content, tokens or privileged action URLs. Existing outbox handles
recipient enrollment, delivery, ACK, dedupe and retries. This module cannot send.

Usage records have exactly run_id, provider (XUANJUN/TENANT/DEDICATED_CUSTOMER/
INTERNAL/UNKNOWN), counters and evidence_sha256. Counters contain model_calls,
input_tokens, output_tokens, cpu_seconds and memory_mib, nonnegative integers or
null. CPU and memory units must be rounded UP by collector. Counters are cumulative
per run; caller reconciles multiple samples first. Identical duplicate runs collapse;
conflicting samples reject. Null or unbound evidence poisons the affected totals.
Memory sum is sum of run peaks, not concurrent usage; native chat quota attribution,
remaining quota and pricing remain UNKNOWN. Missing runs cannot be detected here.

Handoff expected binding has exactly task_id, spec_sha256, checkpoint_sha256,
commit and artifact_sha256. Observed adds evidence_sha256 and literal booleans
old_writer_stopped, descendants_stopped, old_fence_revoked, effects_reconciled,
successor_ack, successor_lease_valid. Every binding must match. Caller verifies
proof freshness, actual lease/fence/epoch, identities and side effects, and performs
the atomic transition. Digest format/booleans alone prove none of these.

## Completion path retained by Work

1. Freeze source, targeted local tests and exact hosted CI receipts.
2. Independent QA/security reviews of exact commits; Work fixes findings.
3. Map live canonical producer fields without inventing missing values. Review
   with shared path owners before connecting their controller/dashboard/outbox.
4. Integrate only under authorized path ownership and valid dependencies; keep
   P2 unique writer and existing runtime authorities.
5. Version-bound UK runtime cases and restart/failure tests, then independent
   acceptance. Source tests never close these nodes or grant deployment.

Current scope has no external writes, model calls, sender, persistence or process
launch. UK Python3.6.8 and live producer mapping/integration/acceptance NOT_RUN.
These functions raise fixed ValueError codes or return HOLD for malformed inputs;
caller handles rejection visibly instead of dropping a task or substituting zero.
