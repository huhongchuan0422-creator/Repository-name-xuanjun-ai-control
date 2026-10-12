# Native controller source candidate — NOT INSTALLABLE

Implemented request-scoped Gateway handler, existing SQLite ledger CAS/guard/expired-lease stop lookup, private importer snapshot manifest, session/unit receipt binding, SDK host adapters, model transcript metadata checks, fixed PR17 notification, plugin entrypoint and transport. No new task registry or queue.

Local tests: 21 Python wiring + 11 real SQLite tests PASS; JavaScript parser/authorization/lifecycle plus real snapshot admission PASS. Gateway/OS calls in local tests are mocks.

UK zero-model readiness run38264025471/job114861499196: Docker binary exists, current config primary openai/gpt-5.6-sol and fallbacks=[], no explicit worker sandbox configuration. Follow-up38264369797/job114862678165: assumed main auth-profiles path absent; this does NOT prove OAuth is absent. Installed API runtime.config.current() and modelAuth.ensureAuthProfileStore/order verified from source. No OAuth values logged.

Remaining: exact immutable host SDK dependency manifest and installation permissions; verified effective OAuth metadata/dispatch path; sandbox config/image/worker UID; tool-hook context run/session fields verification; packaging/deployment manifest and units; same-artifact QA/Security/Release; installation/rollback/real E2E. No source CI or local test grants installation permission.
