# Owner Evidence Preview V1 — nonproduction component
- This is a tiny **read-only offline evidence renderer** for Stage 1 node 1.10 to unblock interface/test work with zero Codex usage.
- It reads an explicit whitelist of public-to-Owner canonical metadata and optionally sanitized task cards. It is NOT a replacement for Canonical State, Task Registry, existing authenticated Owner Portal, Telegram adapter or Admin Console.
- NO web listener, no network access, no external messages, no system service, no production data, no credentials.
- Adoption gate: first audit Tokyo/Domestic existing portal and Node Registry, then reuse its authentication, authority and design before wiring the UI. This HTML must NOT be published on a public web server.
- Follow-up: replace file-only preview with authenticated backend adapter once existing backend schema and ACL evidence are verified. Add Owner notification intents to existing Telegram outbox after verified identity/permissions, without Codex dependency for delivery.
- Testing: `python3 -m unittest discover -s tests -p 'test_owner_evidence_preview.py' -v`. Do not label Stage 1 node 1.10 as delivered.
