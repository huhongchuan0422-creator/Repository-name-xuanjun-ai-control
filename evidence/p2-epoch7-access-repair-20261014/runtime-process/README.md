# P2 retained recovery: bounded runtime child processes

FEATURE_ID: P2_RETAINED_RECOVERY. Same canonical PR17 task and PR58 review path.
This is an in-progress source checkpoint; not an installable complete kit,
independent release approval, actual UK test, or production acceptance.

Two reachable defects were reproduced with harmless local children:
- ledger_server_identity.OSBackend.unit could leak a child when selector setup
  failed before entering cleanup.
- native_gateway_controller.GatewayController._run killed only its leader after
  timeout, then collected output without a deadline. A descendant retaining the
  pipe could block relay preflight indefinitely; output allocation was unbounded
  until communicate finished.

One shared finite primitive now starts an owned private session, bounds both
streams during collection, retains child lifetime ownership using WNOWAIT and the
Popen wait lock before group signalling, and independently closes/reaps within a
finite budget. Cleanup does not claim escaped descendants or production cgroup
containment. Kernel suspension or synchronous kernel stalls are not hard-real-time
bounded by a Python deadline. Genuine partial-output, setup failure, interrupt,
closed-pipe/live-child, exited-leader/held-pipe and overflow tests are included.
Gateway executable verification also rejects nonregular, alias, authority and
concurrent byte changes before spawning, with a32MiB bound.

Python3.6.8 local root-coordinator rerun:72/72 PASS. The count is31 new process/
Gateway tests plus41 existing ledger identity/protocol cases. Separate worker
Python3.12.14 run also passed72. These are local tests, including actual harmless
subprocess fixtures; no Gateway, models, production server or UK command ran.

Compared to frozen v4:107 runtime files =85 unchanged +17 changed +5 added.
Manifest26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa.
Other accepted unchanged evidence remains reusable at its exact byte version.
Downstream rendered units, policies, recovery plan, kit and new approval must bind
this new source; no historic approval authorizes it.

Explicit deferred surface: root_broker._show status/stop request handling still
uses the legacy subprocess.run timeout path. It is not invoked by this recovery
sequence or acceptance (stager runs --help only; service containment uses its own
bounded runner). Do not claim that unrelated runtime request surface has passed
this audit or use broker status/stop as a recovery probe.

All three dispatcher ExecStart/ExecStartPre controller pins were regenerated
to the repaired controller SHA;4 additional local binding/inventory checks pass
on Python3.6.8. These four checks use local baseline paths and are not claimed as
portable hosted CI tests. No other runtime file differs from the d03 checkpoint.
