# P2 r6 saved mechanism evidence — unsigned review inputs

FEATURE_ID: P2_RETAINED_RECOVERY. Original task PR17; independent review PR58.

This is the exact strict-schema metadata export from the Owner's saved successful eight-case probe. No probe, collection, approval fetch or production recovery was performed by the exporter. It omits the full private observation, private configuration bodies, environment values and business/customer data.

- File: saved-mechanism-evidence-1311b9e9fa97cfd4.json
- Bytes including final LF: 289252
- SHA256 including LF: 365d4d361907b3687bf5f444b7d329e484b372563c58be0dcaa8f2bf1da2803d
- Canonical JSON without final LF: 289251 bytes, SHA25692dab6479bb248859ae5e5972fc268aeb0312b464786e2f27c8ecbfa60047dd5

The companion verification receipt records local recomputation, not Work/ChatGPT final approval. Cases1–5 and7 passed; cases6/8 produced the expected bounded rejection. Six units were stopped/empty and34 files removed. Original isolated probe production-process admission remained NOT_VERIFIED.

## Reproduction
Use the exact source in commit09984e00b446f74549480516778fedd85f94bed2 under evidence/p2-epoch7-access-repair-20261014/saved-probe-evidence-r6/. The offline verifier authenticates the kit and topology projector; it does not fetch a review or operate a server.

Run Python3.6+ with -I -B -S and these three positional paths:
1. This exact JSON file.
2. Frozen epoch7-kit-0c8a0f2a.tar.gz from publication1b7d382acc9e78d907b42f20d39b74b913e098f4, SHA256600dc31aaf639aee875be1a075c7b544b9c8c5210fee24013ce614bc69ad5a83.
3. epoch7_topology_projection.py from preparation-source-r6-contracts publication8ab751a84922b76b80c8e8641cbe96e82fa5d391, SHA256f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854.

Command form: python3 -I -B -S verify_exported_evidence.py EVIDENCE_JSON FROZEN_ARCHIVE EXACT_TOPOLOGY_SOURCE

Expected state: PASS_EXPORTED_SUBSET_ONLY, seven exact recomputed digests, whole_observation_recomputed=false and approval_issued=false. The host exporter privately authenticated the full observation with frozen validators. The full observation hash is a host-authenticated binding, not independently reproduced from this subset.

The nested unsigned_expected_review_body is a proposed first topology-only review payload. It is not a signed review. The topology-only acceptance, subsequent private-plan compilation and final exact one-attempt recovery approval are still pending. No installation or production acceptance is asserted.
