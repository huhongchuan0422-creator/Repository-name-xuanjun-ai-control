# B5 isolated read-only capability profile

Owner authorization: PR17 #6286813385, 2026-10-20. Baseline caa752170cb0c6b25be2ea02c62341e5735a4352. This is the newly authorized capability-description function, not original execution-control or P2 end-to-end acceptance. Source/test development only; UK loading/call remains separately confirmed and NOT_EXECUTED.

## Independent version and reuse

`production/p2_b5_readonly_plugin/` is version `0.1.1-b5-readonly.1` of plugin id `xuanjun-p2-native-controller`, with a **metadata-only entry**. It reuses the original id, Gateway registration contract and exact authenticated `operator.admin` client scope check. Original11-file plugin/archive, loader contracts and snapshot code are unchanged. This new profile does not import/register the legacy execution entry, host bindings or ledger module; it does not claim those original methods are installed. Do not co-load this same-id profile with the original plugin or replace a production/Gateway installation in this task. It is an isolated independently packaged B5 version, not a second execution Writer.

The original three-method/version0.1.0 registry validator remains tied to that original profile. It is not silently relaxed to accept this new one-method/version0.1.1 profile. Future real-loader acceptance must explicitly bind the new artifact/version/method and authenticated dispatcher; that work is not proved by these tests.

## Input/output and authentication

Gateway method: `xuanjun.capabilities.describe`; scope `operator.admin` via the real OpenClaw `registerGatewayMethod` descriptor, matching original `index.mjs`. Manifest retains `gatewayMethodDispatch: ["authenticated-request"]`. Only the real dispatcher may supply `client`; no request field is authentication. Handler additionally requires dispatcher client.connect.scopes be an array containing operator.admin. operator.read/write alone, absent client or a string pretending to be scope array are denied. No new network/auth endpoint or credential mechanism is introduced.

Exact params:

```json
{"operation":"describe"}
```

No extra keys, binding file, path, token, scope override, execution verb or inherited operation is accepted. Auth failure is UNAVAILABLE/HOLD_ADMIN_REQUIRED; invalid params is INVALID_REQUEST/HOLD_DESCRIBE_PARAMS. Error payloads do not echo supplied values.

Successful payload contains exactly:

- `plugin_id`: xuanjun-p2-native-controller
- `plugin_version`: 0.1.1-b5-readonly.1
- `plugin_source_sha256`: actual SHA256 of this fixed plugin.mjs source file observed once at registration; not a hash of the whole archive or proof of loaded-byte authority.
- `declaration_sha256`: SHA256 of ordered JSON `{plugin_id,plugin_version,declared_capabilities}` using the module's declaration order.
- `declared_capabilities`: only `{method:"xuanjun.capabilities.describe",operation:"describe",read_only:true,required_scope:"operator.admin"}`.

Returned values are immutable; declarations describe this profile only. They do not report production readiness, a COMMITTED install, health status or availability of original execution methods. A handler's digest is informational; the trusted loader/consumer must still bind the actual source and package to a fixed artifact independently. A digest is not an authorization grant.

## Effects and boundary

Registration reads only its own fixed import.meta.url source, using O_NOFOLLOW/nonblocking FD, regular-file/single-link/64KiB bound, bounded read and before/after metadata checks, and computes SHA256. No caller path or config file is read. File immutability/provenance must be supplied by future protected installation; these checks alone do not prove that the ESM loader evaluated the same bytes it later read.

Request handler does no filesystem or network access and calls no runtime, ledger, OAuth, engine, Owner delivery, model, admit/launch, services or lifecycle operation. No background task/timer, persistence ledger, counter/quota or credential access exists. Source only imports node:crypto/fs/url. Request retries are deterministic pure metadata responses; a restart computes the same public result from the same immutable source. It does not recover a runtime registry handle or claim an installation checkpoint.

14 tests cover exact metadata and digest, immutable response, auth guard, strict inputs/no credential echo, forbidden old binding config, deterministic repeated calls, actual new process readback, and a Node permission-restricted subprocess that can read only this module and is denied a forbidden fixture path. Captured register/dispatcher/client fixtures are **UNIT_CONTRACT_FIXTURES_ONLY**, not real Gateway authentication, real SDK import or CP11 evidence. Existing Node22 in Hosted can run these units but does not satisfy actual OpenClaw engine; target remains existing compatible Node>=24.16<25 or>=26.1, to be bound from source snapshot. No runtime installed in UK or Hosted for this work.

New workflow `p2-b5-readonly-profile.yml` runs only this independent test directory and packages the3 new profile files, mode0444/root metadata, into a deterministic archive plus SHA manifest. It does not repackage the old plugin, old candidate or old contract. No installer added. Read-only metadata profile packaging is not UK installation.

## Approved candidate A remains frozen

Complete original command: `docs/p2-b5-20261020/SNAPSHOT_CANDIDATE.sh` at caa75217, SHA256 `1ef3e0660b0eab3b2aafc5261dc62dbe63a8f8981bc3634d89068c6dec7bb346`, unchanged byte-for-byte. Its historical candidate/not-approved comment is deliberately preserved to keep the approved hash; current approval is PR17 #6286813385. Only Owner runs it via original UK SSH. No new command body, scope, directory, collector source or permission is substituted by this task.

Return the complete terminal stdout/stderr and actual command exit, including host_result and host_result_sha256 (or the original early error if no receipt). Expected final exit2/HOLD is intentional even when bounded source capture completes; check capture and unresolved fields, not just exit code. All output stays at `/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020`; keep pending tar, manifest/result and logs; do not repeat or delete on HOLD. The command prints references to result/archive/manifest and log SHA; it does not print or upload source bytes or secrets. If logs/results are missing or truncated, mark UNKNOWN and list only the missing receipt; do not invent success or ask to run the full source acquisition again.

No original raw UK result has been received in this task: A actual execution remains NOT_EXECUTED. B5 SDK/dependency closure and real named export remain UNKNOWN/HOLD. New function source does not solve those by itself. UK import, real authenticated positive call, B6/B7/P3 and production are not performed or approved by this source delivery.
