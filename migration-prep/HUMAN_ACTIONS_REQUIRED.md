# One consolidated Owner/administrator evidence node — C7 F3-F5

No plaintext password, API key, secret, token, cookie, private key, TOTP or
remove token is requested. Use protected administrator/SecretRef channels only.
This node is read-only. It does not authorize installation, retirement, exchange
access, Shadow, Canary or cutover.

## A. Evidence the current executor cannot obtain

1. **GitHub administrator — Runner admission export**
   - Provider: repository or organization Owner with Actions/Runner administration read.
   - Operation: export Runner IDs `4` and `3`, exact names
     `xuanjun-tokyo-readonly` and `xuanjun-korea-binance`, repository/organization
     and Runner Group membership, allowed repositories, public/fork/PR/workflow
     admission, labels, active jobs and every other Runner/channel able to reach
     either host. Include collection epoch and GitHub-generated object IDs.
   - Return: original API/UI export bytes through the private evidence channel plus
     its SHA-256; do not paste policy bodies or tokens into the public PR.
   - Impact: read-only API/UI access; no job cancellation, label/group change,
     token generation or Runner exit.

2. **Tokyo and Korea root administrator — bounded collector**
   - Provider: host root through the existing Owner-controlled one-shot route.
   - Preconditions: independent source review of `c7_root_inventory.py`; exact
     candidate commit/tree/artifact hash; collector copied to a root-owned,
     non-symlink, non-group/other-writable temporary path. Do not extend the
     persistent `githubrunner` sudo grant.
   - Operation on each host: verify file/path owner, mode and SHA-256; invoke the
     zero-argument collector once as root; preserve original JSON bytes and exit
     status. It inventories root/yibi/githubrunner crontabs, both systemd roots,
     user-unit files reached by those roots, parsed sudoers sources and effective
     githubrunner grant shape.
   - Required result: `PASS_COMPLETE`, zero incomplete outcomes, every root recorded,
     and separate cron `CONFIRMED_NO_CRONTAB` or `READ`; any permission/read/link/
     nonregular/drift outcome remains HOLD.
   - Impact: bounded metadata/content reads and hashing only; no cron/systemd/sudoers
     write, service control or privilege expansion.

3. **Gateway administrator — global trigger export**
   - Provider: authenticated OpenClaw Control UI/Gateway administrator.
   - Operation: export all enabled and disabled automations, cron declarations,
     stream/event triggers, task owners, target agents, execution identities and
     routes that can invoke Tokyo/Korea, Yibi or Writer code. Include collection
     epoch and original export SHA-256.
   - Required result: administrator-global scope marker and complete pagination.
     The caller-visible two-job list is not acceptable.
   - Impact: read-only export; no trigger enable/disable/edit.

4. **Independent Authority custodian — existence/read-only measurement**
   - Provider: independent key/authority owner, not the Developer or executor.
   - Operation now: attest whether an Ed25519 trust anchor, Authority record and
     detached policy signature already exist; return public identity/fingerprint,
     exact policy/commit/tree/epoch/expiry binding and protected record metadata.
     Do not create a new key/signature in this read-only node.
   - Required result: original public record bytes and verifiable signature, or an
     explicit `NOT_PRESENT`. A Developer-created key cannot count as independent.
   - Impact: read-only authority inspection; private key material never leaves custody.

5. **Korea root administrator — pre-install environment readback**
   - Provider: Korea root through the existing Owner-controlled route.
   - Operation: inventory the existing dedicated user/group (if any), install/data/
     evidence directories, Python/runtime dependencies, unit names, candidate ports,
     protected SecretRef metadata (names/roles only), proxy/environment presence and
     root egress/firewall state. Bind original output to host and collection epoch.
   - Impact: read-only. No user/directory/unit/package/SecretRef/firewall/IP change.

   Existing-authority refresh already identifies 443 as
   `morelogin-socks5-permanent.service` (`gost`, PID 996). The administrator return
   must confirm its current socket/cgroup identity and coexistence boundary; it must
   not stop, replace or reconfigure MoreLogin as part of read-only evidence.

6. **Independent verifier custodian — actual code measurement**
   - Provider: administrator independent of the executor result producer.
   - Operation: measure the real loaded verifier executable/module, canonical path,
     resolved non-symlink parents, owner, mode and SHA-256; prove which service/process
     loads it; identify the independent post-state data source and its authority.
     Bind those measurements to the exact action and receipt epoch.
   - Required result: installed-file and live-loader measurement. A verifier hash
     merely written in a signed request remains candidate-only.
   - Impact: read-only process/file inspection; no install/restart.

## B. Owner decisions requested once

Confirm or replace all values; blanks remain HOLD and are not inferred:

- Shadow duration: proposed `24h` (not yet executed).
- Shadow acceptance: zero unknown/inflight/ownership conflicts; complete BTC/ETH/SOL
  coverage; zero Writer effects; restart/recovery test PASS.
- Canary: maximum notional/order count, exact duration and stop threshold.
- Korea-first rollback deadline and maximum time before Tokyo recovery may be considered.
- Maintenance window, evidence root, independent Authority custodian and approvers.
- Resource acceptance thresholds for the minimal Binance runtime (OOM/restart,
  MemoryAvailable/swap delta, CPU/latency, disk/inode/FD). Do not answer with an
  expansion purchase; existing Korea capacity is evaluated first.

Replying with thresholds fixes review inputs only. It does not authorize production.

## C. Later write stages — separate exact Release Gates

The package prepares, but this batch does not execute: trust-anchor/signature policy
creation; verifier/runtime install; default-deny egress; SecretRef creation; Runner
exit; database freeze; live Binance GET; Shadow; Canary;
Writer epoch transfer; credential/IP revocation or cutover.

Yibi stop/disable/mask is not a migration prerequisite. It becomes a separate exact
post-acceptance Gate only after Binance migration PASS and archive revalidation. Before
PASS, an alleged conflict must name the exact unit/process/port/path, direct impact and
smallest isolated action; project-wide Yibi shutdown is forbidden. Novel remains in
place and must not be started, stopped or deleted by this migration.

Every future authorization must bind the exact artifact, commit/tree, host, path,
unit, action, transaction/epoch, expiry and single-use nonce. Timeout, partial success
or unknown result means stop, independently inspect side effects and reconcile; never
blind retry or replay a completed effect. Rollback order is Korea Writer locked →
Korea credential/IP revoked → unknown outcomes reconciled → only then evaluate Tokyo
checkpoint/read-only recovery and a new Writer epoch.
