# Observation-bound r6 proposal delivery candidate

This separate candidate preserves the previously reviewed disabled delivery
checkpoint. It binds the exact three r6 preparation sources published at
e8b9ebb3fb215fa5b1ef0a8dc0b31a77efd0ab67 and the genuine same-attempt observation
1311b9e9fa97cfd4, SHA256
b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246.
The helper rejects a different path or hash before host or network checks.

Manual Owner execution has a limited filesystem effect: exclusive creation of
one 0700 r6 preparation directory and exactly three 0600 source files, or reuse
of the identical complete inventory. A partial creation is retained and reported;
there is no overwrite or automatic cleanup/retry. The fixed staging destination
matches the reviewed preparation wrapper's epoch7-preparation-candidate-r6 path.

The sole operation is propose-topology. The pinned preparation code validates
all eight cases and their protected receipt, Node proof, peer identities, SDK
bindings, namespaces/readpaths, posture and expected denials. It returns the
exact unsigned expected_review_body, topology digest, preparation source
manifest and drop-in inventory. This is an unsigned proposal plus host-validated
evidence bindings, not a complete independently reproduced audit packet. Root
will assemble the full source/test/actual-receipt links separately. Hashes alone
do not establish independent raw-case verification. It does not print raw
private evidence or the derived topology object. An actual returned proposal remains pending manual
Owner execution; local fixtures do not establish actual host proposal success.

No prepare/resume argument, final approval, topology approval or private-plan
compilation is allowed through this delivery endpoint. Genuine topology review
is required before any subsequent private-plan work. Production remains HOLD.

The helper's preparation and observation bindings are enabled, but the owner
bootstrap remains unbound to its own delivery commit/hash/size. Root must first
publish the reviewed helper and bind those exact publication fields. No delivery
publication ID has been invented. The template is not a ready-to-run command.

All 41 focused tests pass on Python 3.6.8 and 3.12.14, with zero skips. They retain
the previous 39 cases, adapt the two explicit binding assertions, and add
mismatched-observation refusal and prepare/resume argument refusal. Network
responses and flow calls are mocked; filesystem effects use temporary fixtures.
No host operation, actual download or private-plan preparation was run here.
