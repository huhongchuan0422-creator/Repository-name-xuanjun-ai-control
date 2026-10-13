# Control service observations — source only

PR17 registration6136334713, V2.7 1.6/1.10. Existing Owner dashboard currently
reports UNKNOWN service placeholders; this module supplies a narrow collector
for later integration, not a new dashboard, daemon or health authority.

observe_service(unit, run=None, clock=None) invokes exactly /usr/bin/systemctl
show for one of three fixed existing services, requesting only Id, LoadState,
ActiveState, SubState, MainPID, Result. No shell/sudo/environment dump/log command.
The subprocess has a 3-second timeout, discarded stderr, no stdin, fixed minimal
environment. Unknown units reject before any call. The tool is NOT invoked on
hosts in this source PR: tests inject a fake runner, including errors/timeouts.

Parser requires exactly those six properties once, matching unit ID, bounded
UTF-8 output, known enums, numeric PID. Unknown/future systemd values remain
UNKNOWN until separately reviewed, never assumed healthy. Failure reason strings
are fixed and do not echo command output or secrets. OBSERVED means properties
were read, not service health PASS. ActiveState=failed remains explicitly failed;
active/running is not model readiness, authenticated API access, or task progress.
The module reads no task leases and cannot authorize mutation or claim execution.

The integration owner must run under an approved read-only local identity, bind
host/boot identity and timestamp outside this module to the trusted evidence
collector, and apply display freshness. This observer does not authenticate a
host or verify unit binaries. No root service mutation, credentials, new auth or
runtime model/provider call. Existing root_broker/legacy_quiescence authority and
stop observations remain unchanged. Source reuse inspection is not a fresh
Tokyo/Domestic/UK host scan. Actual host integration and UK verification NOT_RUN.

Run python3 -B -m unittest discover -s tests -p test_control_service_health.py -v.
Python3.6+ standard library only. No overall node/installation/release PASS.
