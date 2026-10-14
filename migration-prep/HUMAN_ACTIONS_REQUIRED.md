# Single consolidated human cooperation node for C7

No plaintext password, API key, secret, token, cookie, private key, or TOTP is
requested. Complete the following only through protected administrator/SecretRef
flows after independent source review and a new Owner Release Gate.

The Developer has completed the private-map digest/ID verification, caller-scope
Gateway inventory, fixed-helper Tokyo/Korea baselines, Korea pre-install baseline,
independent post-state verifier, redacted root inventory candidate and deterministic
execution package. The following cannot be completed with the current authority.

1. **GitHub Runner administration (read-only now; removal later)**
   - In repository/org Settings → Actions → Runners, export or privately attest Runner
     IDs `4/3`, exact names, repository/group assignment, pool, allowed repositories,
     fork/PR admission and any other Runner with these hosts/labels.
   - Impact now: read-only evidence only; no job cancellation or Runner change.
   - Later, after a new Release Gate, issue two scoped short-lived remove tokens through
     protected masked entry. Never paste them into PR, Feishu, files, shell history or logs.
2. **Bounded root read-only evidence on Tokyo and Korea**
   - Independently review `c7_root_inventory.py`, then install/invoke it through a
     one-shot root-controlled route bound to the exact commit/artifact; do not add a
     persistent broad Runner sudo grant.
   - It reads root/yibi/githubrunner crontabs, systemd metadata and sudoers source
     closure, emitting only counts/digests.
   - Impact: read-only CPU/disk reads; no service, cron or sudoers modification.
3. **Gateway-wide triggers (administrator read)**
   - From an authenticated Control UI administrator turn/Automations page, export all
     enabled and disabled automations, stream triggers, declaration jobs and owners.
   - Impact: read-only export. Caller-scoped output is explicitly insufficient.
4. **Independent trust and Authority** — provision an independently managed Ed25519
   public trust anchor, publish its fingerprint through a protected authority record,
   sign the exact canonical policy/manifest, place policy/signature/anchor in the
   reviewed owner-bound non-symlink paths, and bind any future request to exact host,
   execution identity, paths, units, action, candidate hash, expiry and nonce.
5. **Owner decisions (reply once after reviewing the exact package)**
   - Approve/change: `Shadow=24h`; zero unknown/inflight/ownership conflicts; exact
     BTC/ETH/SOL symbol coverage; zero Writer actions; restart-recovery PASS; proposed
     canary duration/size; Korea-first rollback timeout; evidence root; maintenance window.
   - Impact: fixes acceptance thresholds and scheduling only. It does not itself
     authorize deployment, live Binance GET, Writer activation or cutover.
6. **Root network isolation (later production change)** — install and independently inspect the dedicated
   runtime's default-deny egress, pinned DNS/IP set, credential scope, unit expansion
   and absence of alternate clients/transports. Application GET checks alone are not
   accepted as network isolation.

7. **Protected SecretRefs (later production change)**
   - Create only the approved read-only Binance credential namespace and any required
     independent signature reference through masked administrator entry after Release
     Gate. No trading/withdraw permission.
   - Impact: credential and IP-policy change; therefore not executed in this batch.

After items 1–5 return, an independent reviewer can decide whether the exact install/
Shadow execution scope may enter Release Gate. A separate fresh Owner authorization is
still required for items 6–7 and for Runner exit, Yibi retirement, production DB freeze,
live Binance GET, Shadow/Canary, credential/IP changes or Writer authority.
