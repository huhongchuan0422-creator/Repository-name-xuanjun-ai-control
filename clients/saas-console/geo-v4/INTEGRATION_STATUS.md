# GEO V4 Customer Integration Status — 2026-11-03

## Frozen source authority

Sites project: appgprj_6ae8cd2496188191a100ab382ac88e31
Sites version: 4
Sites prototype SHA: 842cc9707600aa3d47ad517ca67d14d0ffb31246
Main-repository handoff commit: 45b4f17da2fee562274ba4ee2cd43722031a148e
Source directory: handoff/geo-v4-customer

The four V4 implementation files are copied byte-for-byte into this directory and remain frozen:
- index.html SHA256 39ba7edef950d05c3ab32c626ff2eb19f00007e5a0e231316103a6ae1ea08456
- styles.css SHA256 90bb08cecbfc8c6033497dad09b6cb1c70a9d6a1c767910703ebf9868acf899a
- ecosystem.css SHA256 d9973bfc62cc3ee4facce90fa08b299c8701e1746059ccfc59358ea9e6cdb79a
- app.js SHA256 d6aa15803319ff60b7ec3b073f73eb85a65d2494d89a7cdf68070504700b6822

live.html differs from frozen index.html by one module script only:
../src/geo-v4-runtime.js

No V4 CSS, layout, frozen app code, navigation, wording, or functions are redrawn or deleted.

## Current real integration

Connected now:
- existing SaaS same-origin identity via /customer/center/api/me;
- project membership / role / tenant / customer context;
- cross-tenant rejection in geo runtime;
- existing GEO customer state model in src/geo.js;
- safe NOT_CONNECTED / UNKNOWN handling;
- no blind retry for unknown task outcomes.

Not found in the current repository as a customer HTTP contract:
- GEO entitlement purchase/activation;
- GEO Billing/Usage quota;
- GEO diagnosis/evidence service;
- GEO optimization task service;
- GEO version comment/confirmation service;
- GEO effect/result service;
- next-round task creation.

Backend/service owner for those missing contracts: UNKNOWN from current repository evidence. The separate backend-management responsibility must provide the authoritative service contract; this customer-side writer will not invent it.

## Frontend adapter seam

window.__XJ_GEO_CUSTOMER_SERVICE__ is only an internal frontend adapter seam, NOT a claimed backend endpoint.

Required read method:
snapshot({project_id, tenant_id, customer_id})

The adapter must map the authoritative backend response into the already-tested geo.js customer-state model. Until an authoritative adapter exists, the runtime reports NOT_CONNECTED, masks demo metrics as unavailable, and blocks demo mutations from creating false customer actions.

No secret, new credential, server access, production deployment, new billing system, second identity system, or second task system is created here.

## Visual verification limit

The frozen source is byte-identical to V4 and live.html adds only the runtime module. A new browser screenshot comparison is not claimed in this environment because Chromium navigation remains administratively blocked by ERR_BLOCKED_BY_ADMINISTRATOR and no bypass is used. Source/hash parity is verified; browser visual E2E remains NOT_VERIFIED.
