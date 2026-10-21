# Two implementation analysis candidate — NOT installation

Parent: 4fb10937d260d15f03b986599c5a75a90ecca474. Metadata: PR17 #6314958023 and exact attached JSON saved in evidence; SHA256 6c749d73a07f6bfe3311cd68068e69d0682d67317f8e990f475f9942c0b8298f.

## Fixed selection and actual parent references

| Target | Bytes | Parent reference |
|---|---:|---|
| dist/server-plugin-bootstrap-BF-wNIVo.mjs | 3726 | verified server-startup-plugins-Cajv-q3y.mjs line 182: dynamic import; prepareGatewayPluginLoad called immediately below |
| dist/server-startup-config-helpers-d2nPJiVj.mjs | 11278 | verified server-startup-config-Hx2M1x7s.mjs line 11: named imports of snapshot, overrides, source and weak-auth helpers |

Exactly two / 15004 B, both absent from existing extracted materials and attested absent from original 1718 package. These dynamic/native implementation bodies are the immediate missing inputs for this analysis step. Existing four files/client, core, shutdown, inspection and WS bytes are reused. No recursive selection, no 384-member collection. Dependencies of unread implementations remain UNKNOWN, so this is not a final installation dependency list.

## Questions this candidate permits answering after receipt

- Read actual prepareGatewayPluginLoad selection/activation/registration and retirement behavior; establish how native startup's own registry is built. Does not itself prove active registry or load plugins.
- Read actual config snapshot loading, source precedence, auth overrides and weak-auth assertions; determine whether a restricted native startup profile can be frozen without touching excluded production auth or providers. Does not itself authorize credentials or suppress native checks.
- Newly discovered mandatory implementation dependencies, if any, must be bound from original manifest before a subsequent candidate; do not guess bytes/SHA or substitute a fixture.

## Complete operation candidate

The frozen command is implementation-pair.command; size/SHA and bootstrap Git blob are in implementation-pair-candidate.json. It downloads only the fixed verified tool blob via GitHub (not SDK). On original UK host/root/Python 3.6.8 it creates exactly two new admin-private directories listed in that JSON, writes protected bundled tool files, drops to admin for reading the original retained tar/manifest, verifies original full inputs and all member content, prechecks both target manifest bindings before selected reads, then writes materials.tar/report.json/receipts. New dirs 0700/files0600; no existing permission changes.

Original dirfd/O_NOFOLLOW/O_EXCL protections, AS768MiB, CPU180s, child240s/parent270s deadlines, FD128, core0 and FSIZE20MiB stay unchanged. Selection16MiB/report2MiB/tar18MiB bounds unchanged. Outputs or directories existing => HOLD and retain; no delete/rename/overwrite/automatic retry. Failures preserve partial outputs. No SDK/Node/parser, Docker, model, service, production access or B1–B4 changes. Host fetch is a network read and new files are writes, not a zero-side-effect query.

## Readback and recovery

Specific Owner confirmation is required before this new UK action. NOT_EXECUTED. After one execution collect full terminal JSON and both output files; check actual archive/report digest, exact two regular members/pins, and original_inputs evidence. Output hashes are UNKNOWN until execution. Failure retains fixed output checkpoint; diagnose retained receipts, never rerun blindly. Successful material collection is not dependency closure, authentication or CP11 success.

## Validation

New targeted tests only; old successful unchanged source tests are reused. Local Python 3.12: 7 PASS; Python3.6 AST parsing PASS. Hosted Python3.6.8/3.12 status recorded separately in PR17, never inferred from local parsing. No UK operation.
