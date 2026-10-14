# Dispatcher pre-start ACK regression

Actual production unit `deploy/xuanjun-development-dispatcher.service` runs
`stage1/p2_service_context_preflight.py` in ExecStartPre. That script requires a
`dict` with literal `ready=True`. `NativePipelineRuntime.preflight()` already
validates ready/canonical_existing/isolation_enforced/outbox_existing but omitted
its return, so the script rejects a valid controller ACK with HOLD_PLUGIN_PREFLIGHT.

Minimal fix: return the already validated result. No flag relaxed, controller
call added, task claimed, model invoked or outbox notification sent.

CPython3.6.8:7 local tests PASS. Two tests against original checkpoint source
reproduce the defect (one assertion failure, one SystemExit). Tests invoke the
actual service main with mocked identity/config/controller boundaries; they are
not real Gateway RPC, UK startup, production acceptance or independent approval.

Runtime remains107 files:87 unchanged,15 changed,5 added relative to frozen v4.
Manifest f092f04d103c6eb26fdc8c380509a7c87113d7c5bd00ee5c80f9af7559db4638.
This is an in-progress source checkpoint, not a recovery package or review request.
