# UK mechanical P2 canary trigger — 2026-10-12

Source-only trigger for the already Owner-installed **V2** inert bridge. The scoped branch push intentionally starts the existing UK self-hosted GitHub Actions canary; it creates only one bounded inert inbox request, waits up to 90 seconds for the independent systemd service receipt, and reports the outcome to PR #17.

Pin installed bridge SHA256: `9a6f33c332284412f98ef9f82c94363b4c5caa4ceb5d8cea835bd94de14e99b9`. The Owner-reported V2 install returned `P2_MECHANICAL_INSTALLED_ONLY_NOT_P2_PASS`; this test validates but does not presume the service works. No model calls, no developer/ledger writer, no production mutation. Python runtime is target `/usr/bin/python3`; compatibility acceptance remains pending real UK host results.

P2 final dispatcher/broker/ledger and P3 two-task E2E are still HOLD. This does not admit privileged installation, model inference or releases. This trigger must not be re-created under another filename if the Runner response is missing; reconcile the current GitHub run first.
