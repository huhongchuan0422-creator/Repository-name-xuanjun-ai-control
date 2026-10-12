# Native controller source candidate — NOT INSTALLABLE

Implemented Gateway plugin-owned handler and host adapters, existing ledger socket/CAS/synchronous guard, expired-lease stop lookup, source tree verification, model transcript metadata checks, native transport hash activation binding, tool run/lease/unit hook, read-only QA tool deny, and fixed PR17 notification. No new task registry, database, queue or scheduler daemon.

Local tests: 21 wiring +11 actual SQLite +7 socket-role/parser tests PASS; JavaScript controller lifecycle/real snapshot tests and9 host policy assertions PASS. Gateway/OS operations are mocks in these tests.

Hosted CI38265743841/job114867330810 on288ba340 passed the earlier frozen-source replay (21+11 Python and controller JavaScript). Later socket/host changes require their own commit-bound CI.

UK readiness38264025471 and38264369797: existing Docker binary, primary openai/gpt-5.6-sol, fallbacks=[], no explicit worker sandbox configuration. Assumed main auth-profiles path absent is NOT evidence OAuth is absent. Installed SDK contracts38266313384/job114869259709 verify runtime.config.current(), native modelAuth metadata APIs and hook event.runId. All reads zero-model, no production/lease changes.

Installation HOLD: actual OAuth/runtime dispatch, sandbox config/image/UID and read-only QA workspace mapping, immutable context module trust, plugin binding/transport config, socket ACL persistence, updated unit/manifest/activation cutover, same artifact QA/Security/Release, install/rollback/E2E have not passed. See HOST_BINDING_GAPS.md. Unknown f998 never replayed.
