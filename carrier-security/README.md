# Carrier security continuation — design hold

This branch is a non-deployable candidate. The original carrier lives outside this
repository and must not be installed. The required controller trust anchor,
pre-execution verification, replay ledger, safe extraction, failure receipts,
and least-privilege MCP changes are not implemented in this branch.

The requested bootstrap must be distributed and trusted independently of the
carrier; a digest computed from carrier-controlled input is not an authority.
Until independently reviewed code and an authorized controller binding exist,
all operations remain HOLD. Do not use the original carrier as a workaround.
