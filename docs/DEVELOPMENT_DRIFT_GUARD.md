# Development drift guard (source preparation)

PR17 scope6135848335; V2.7 node1.11; source writer DOTS. Pure Python3.6+
standard-library adapter, no DB, queue, filesystem, network, process or model.

`evaluate_drift(contract, observation, now)` returns MATCH or HOLD plus fixed
reason codes. MATCH never grants execution. Unknown/malformed evidence is HOLD,
not zero or success. Caller must verify signed contract/path review with existing
entry_review_gate and bind a fresh complete observation from the existing
canonical runtime collector to that same admission. This module does not prove
collector authenticity, atomically stop a worker or enforce a budget by itself.

Contract exact schema DRIFT_CONTRACT_V1:
- identity: task_id, spec_sha256, checkpoint_sha256, base_commit, run_id,
  lease_owner, epoch, fence (all required, exact comparison).
- limits: active_agents, heavy_agents, delegation_depth, patch_attempts,
  model_calls, cpu_seconds, memory_mib; nonnegative integer upper bounds.
- allowed_permissions: unique exact capability identifiers, no glob/prefix match.
- max_age_seconds: integer 1..3600.

Observation exact schema DRIFT_OBSERVATION_V1:
- same identity; usage has all seven counters; permissions lists all effective
  capabilities, including inherited/delegated capabilities.
- observed_at numeric finite Unix seconds, complete=true (literal boolean).

Counter semantics: active/heavy agents are concurrent totals for this admitted
run; heavy is a subset of active. delegation_depth is maximum observed depth;
patch_attempts and model_calls are cumulative for this run including failed or
stopped attempts. cpu_seconds is cumulative CPU rounded UP to whole seconds;
memory_mib is aggregate peak resident memory rounded UP to MiB. A collector that
cannot measure a field must report incomplete/unknown, never omit it or supply0.
Limits use the same units; a zero model_calls limit forbids all delegated calls.
Native chat inference attribution is outside this mechanical collector and is
not claimed to be zero. This module does not choose policy or invent approvals.

All identity dimensions must match. Changed task/run/checkpoint/lease/fence/epoch
requires a new authorized binding; a MATCH does not resume an old writer.
A future/stale timestamp, any excess counter, permission expansion, malformed
schema or impossible heavy count yields HOLD. All valid-input discrepancies are
returned together. Output never echoes raw contract, identifiers or permissions.

Integration contract: runtime owner authenticates inputs, captures complete
counters at the existing transaction/admission boundary, treats HOLD as a
required stop/hold request using existing mechanisms, and retains evidence.
This PR supplies no shared-controller patch and makes no enforcement claim.
Independent review, actual shared integration, UK install and runtime acceptance
remain pending/NOT_RUN. Existing signed path gate is required, not reimplemented.

Test: python3 -B -m unittest discover -s tests -p test_development_drift_guard.py -v
