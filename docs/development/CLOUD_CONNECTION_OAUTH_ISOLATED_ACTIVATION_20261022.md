# Independent OAuth activation package — preparation only

## 1. Bound scope and inherited evidence

PR17 #6331318756 / #6331288141. Baseline 1afaa172610385f87c4f3d223ed8972e397d6e49,
tree 6210baf4a1bdde3cb0e953aceeab776d56b4fb68. Inherit the unchanged 211 cases,
review #6330270020, two-host preflight and CPython3.12.15/20261021 runtime plan.
This increment changes only HTTP01 candidate configuration, its tests, manifest,
CI and this deployment preparation. It does not enroll services or approve itself.

Original App asdk_app_6ad8e68b582881918fcfd3da6e5b65fd and
original tunnel_6ad8e1d2482c8191b542ba8dd38c3545 remain unchanged.
New App + new tunnel is the selected route. Same-ID migration/support is no longer
a prerequisite. New catalog=[], no shell, no business Writer or project roots.
Static-client incompatibility means stop the new chain; no DCR/CIMD rewrite.

## 2. Exact configuration and acceptance

Final nginx-vhost.conf.candidate now puts the fixed HTTPS redirect inside
location /, and serves only ^~ /.well-known/acme-challenge/ from the existing
/var/www/letsencrypt with try_files $uri =404. A server-level return must never
precede the ACME location. All existing HTTPS auth routes and header boundaries
are retained. New nginx-http01-bootstrap.conf.candidate serves the same public
challenge and returns503 for every other route, with no443 or authority proxy.
Bootstrap and final are mutually exclusive: one target vhost, replaced only after
certificate validation. Never load both.

Tests/test_cloud_connection_oauth_nginx.py binds both hashes and tests actual
Nginx syntax/start, challenge200/exact bytes, missing404, final fixed-host308
including untrusted Host, bootstrap503 and challenge POST405. Actual Nginx cases
run only on temporary loopback ports/root/certificate; no production command.
REQUIRE_NGINX_TESTS=1 makes missing binaries fail in the dedicated Hosted job.
Local missing binaries are explicitly SKIPPED/NOT_RUN, never counted as PASS.
Unchanged 211 tests are not newly independent coverage; existing workflow may
repeat them as regression, with counts reported separately.

## 3. ACME, DNS and one renewal mechanism

Bound original source: commit312efdd3eb4d24ff1fceecc480c4ba302bf22073,
deploy/pr122-domestic-website/tls and systemd; original root receipt#6197976903,
automatic-check evidence#6201566573. Historical, not fresh host attestation:
- /usr/local/bin/certbot, expected certbot5.8.0.
- Webroot /var/www/letsencrypt; config /etc/letsencrypt;
  work /var/lib/letsencrypt; logs /var/log/letsencrypt.
- issue-apex-certificate.sh SHA464a564dba4269244f4bcbdad77298b109b891541ec4e29e7c4e92e0ab82f5f7.
- renew-apex-certificate.sh SHAcb2a9e645cff03e04c667c1001b3eec627119a0498395b013324de909d9f357e.
- /usr/local/libexec/xuanjun-apex-nginx-deploy-hook
  SHAadb7d7efd5c4255b7aabefd3a0bc74ae7af0df221e32fcf92bf7044bc13b6be8:
  nginx -t, then systemctl reload nginx.
These apex scripts hard-code the apex lineage: do NOT run them for cloud-auth.

Fixed proposed DNS change: Cloudflare zone wenwenwenyiyiyi.work, type A,
name cloud-auth, content47.101.152.210, proxied=false, TTL300. No AAAA is added.
If the name already exists, contains CNAME/AAAA/conflicting origin, or prior values
are unknown: stop before write and reconcile exact record ID/old values. Do not
change apex, mail, center, wecom, winctl or uk. Zone/record IDs and prior absence
must come from the authenticated normal management read, not public DNS guesses.

CA selection: reuse the currently configured production ACME account and its
exact server endpoint. Neither the non-secret account ID nor server URL was
present in the reviewed receipts. Do not assume a default endpoint or create a
new account. The installation gate requires the exact account/server pair and
existing account registration metadata; account private_key.json must NOT be read.
The new command will be Certbot certonly/webroot with explicit --account and
--server, cert-name/domain=cloud-auth.wenwenwenyiyiyi.work, ECDSA, existing fixed
directories. No --expand, --duplicate, --force-renewal or new account/TOS acceptance.
The presently unknown two values are runtime admission fields, not invented values
or an assertion that the implementation command is already executable.

One selected renewal mechanism: a dedicated new-lineage service/timer,
xuanjun-cloud-oauth-cert-renew.{service,timer}, invoking fixed
/usr/local/libexec/xuanjun-cloud-oauth-cert-renew. Its command is certbot renew
--cert-name cloud-auth.wenwenwenyiyiyi.work with the bound account/server/config/
work/log directories and verified existing Nginx hook. No apex timer modification.
Schedule follows original twice-daily03/15:23 + randomized1800s, Persistent=true.
Enable only if the existing general scheduler does NOT already renew this new
lineage. If it does, stop to select that existing scheduler explicitly; do not
silently enable both or modify shared renewal policy under this package.
Dry-run and actual deploy-hook outcome are separate evidence. Old apex/IP timers
continue unchanged. New certificate lineages and account state are never deleted
as automatic rollback.

## 4. New objects, permissions and protected paths

Keep original org org-YWzeuCqNH5FEU0Mr5oJUyhvU and workspace
0470a707-2a65-4684-8dab-e17f99af61f1. Proposed new tunnel display name
xuanjun-cloud-connection-oauth; actual ID is filled after approved creation.
Creator/operator needs organization Tunnels Read+Manage; runtime principal and
plugin operator need Read+Use, no Manage on the runtime key. These are documented
organization-level permissions: per-tunnel-only key scope has NOT been established.
If normal UI cannot restrict runtime access to the new tunnel, disclose actual
organization-wide tunnel scope before issuing the key; do not claim resource-level
restriction or silently accept broader permissions. No Models/Responses/Files or
other API permissions are needed for this transport. Creator authority is not
copied into runtime credentials.

Proposed key duration: earliest normal supported expiration not later than the
existing2026-11-20 boundary; record exact UTC after approved creation. Actual
current UI expiration choices are NOT_VERIFIED. No permanent duration or extension
of the old credential. A read-only navigation to the organization API Keys page
was rejected by automatic safety review in this round; it was not retried through
another path. Reason: potential credential/sensitive-key-metadata exposure and
current scope forbids credential creation/entry. Official docs establish required
permissions, not this account's enabled choices. This is a remaining issuance
admission check, not a claim credentials have been created.

New UK root-protected objects (all NOT_CREATED):
- profile /etc/xuanjun-cloud-executor/tunnel-profiles/xuanjun-oauth.yaml,0600;
- credential /etc/xuanjun-cloud-executor/openai-oauth-tunnel-runtime.key,0600,
  root-owned/single-link/private parent; never CLI arguments/public JSON/logs;
- unit /etc/systemd/system/xuanjun-cloud-oauth-tunnel.service,root0644;
- client deployment under /opt/xuanjun-cloud-oauth/tunnel-client/ pinned to the
  actual original supported client binary SHA/version, pending metadata binding.
Use the supported client's verified file/env secret reference. No speculative CLI
flags are executable instructions; installed client help and exact binary SHA must
be bound before the final unit ExecStart is admitted. Only HTTP upstream
http://127.0.0.1:18769/mcp; no old stdio profile/upstream changes. Separate unit and
transport process are NOT a second business queue/worker/Writer. Unit hardening
must retain secret isolation and only required outbound443/local18769 access.

Domestic dedicated account xuanjun_oauth/no-login/no-sudo; authority service
127.0.0.1:18770, private state /var/lib/xuanjun-cloud-oauth/authority.sqlite,
config /etc/xuanjun-cloud-oauth/ and immutable /opt/xuanjun-cloud-oauth/.
UK resource service127.0.0.1:18769 with original hardened configuration; approved
runtime archive SHA6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772.
No P2 container/system-Python changes, no new cloud identity. Reuse original lock.

Domestic vhost target /etc/nginx/conf.d/xuanjun-cloud-oauth.conf;
/etc/xuanjun-cloud-oauth/{tls-approved.conf,proxy-approved.conf}; independent
/etc/letsencrypt/live/cloud-auth.wenwenwenyiyiyi.work/{fullchain.pem,privkey.pem}.
Private key bytes never exported. Public authority paths/headers/limits use the
bound candidate; introspect allowlist requires actual UK source as seen domestically.

## 5. Fixed implementation admission, no new host checks performed

Existing preflight authorized environment/ports/fixed-path metadata only. It does
not authorize reading ACME account metadata, DNS management, arbitrary roots, key
pages or new paths. This preparation performs no server commands. One bounded
additional read request must cover exactly:
- Domestic: metadata/hash/version of /usr/local/bin/certbot, Nginx binary/config
  include context for the new fixed vhost; webroot full parent metadata, no listing
  of customer files; exact new vhost/tls/proxy/lineage/unit/script target conflicts.
- ACME: known existing apex renewal configuration projected to account/server and
  fixed production account registration metadata only. If account reference cannot
  be obtained from that config, stop; no account-directory scan/private key read.
- Scheduling: exact original apex/IP and general Certbot unit/timer/cron references
  from existing records; missing exact reference is reported, not broad cron scan.
- DNS: authenticated read of only the new hostname's records plus owning zone ID;
  preserve exact prior values. No write at this stage.
- UK: metadata/version/SHA/help for the original tunnel-client binary referenced
  by the old service, new profile/unit/key/runtime path conflicts; no old key read.
- UK egress: one bound non-sensitive outbound request and domestic receipt showing
  actual source, only through an approved fixed receiver. Existing public IP does
  not prove NAT path; no arbitrary external echo or temporary listener is authorized.
Unknown or unsupported checks stop only dependent actions. No root/project scan,
execution lock, B5/P2 startup, database/customer content or unapproved project root.

## 6. Concrete confirmation and rollback sequence

This is the bounded change set to confirm after incremental review, not a permit:
1. Approve the above fixed supplemental reads; fill account/server/DNS old values,
   actual client version/reference, target conflicts and UK source. No credential
   needed to resolve those non-secret facts; no Owner file搬运.
2. Approve new isolated runtime/source/config/accounts/secret storage, authority,
   resource, tunnel/profile/unit/key with exact permitted expiry and actual scope;
   cloud-auth DNS/TLS/bootstrap/final vhost + one renewal method. Exact unit/profile
   bytes and generated config hashes are captured before their activation, after
   platform-created IDs exist. Old connection continues throughout.
3. Approve normal new-plugin creation/discovery using only the new tunnel and
   OAuth. Record actual new ID/resource/client mode/redirect_uri at the stage the
   platform exposes them. Bind resource in both services; register exact callback
   whitelist. If static-client configuration is unsupported, stop the new chain,
   preserve evidence, do not switch protocol to DCR/CIMD.
4. REAL USER OAUTH CONSENT IS SEPARATE AND NOT APPROVED BY THIS PACKAGE. Stop
   before GitHub/ChatGPT consent submission until explicit applicable confirmation.
5. Then, if approved, real wrong-subject/expiry/refresh/revocation/restart tests;
   no business Writer, no project-file transport until its own catalog/root admission.

Capture original owned-file absence/hash/mode, old unit states and DNS values
before writes. Unknown outcomes query original task/InvokeId first, never replay
sensitive writes because a timeout occurred. On failure stop only new resource/
authority/tunnel/new renewal unit; restore only transaction-owned Nginx and new
hostname DNS snapshots with nginx -t then verified reload. Do not remove ACME
lineage/account/auth DB/logs; do not revert shared Certbot dirs or affect old timers,
old App/tunnel/upstream. Revocation/disconnect of only new credentials/authorization
uses the normally approved platform action. Record side effects/checkpoints.

Incremental independent review scope: changed HTTP01 config+new bootstrap and
actual-Nginx tests/manifest/CI, deployment plan accuracy; inherit unchanged runtime
and original211 cases. This Writer does not self-approve. Approval remains pending.

Remaining facts are exactly the account/server pair, DNS management prior state,
client binary/CLI/secret-reference binding, current key expiry and scope choices,
new target conflicts and real UK egress, plus platform-generated IDs/resource/
callback/client compatibility after approved creation. Source readiness is not LIVE.
Community manual preview remains independent; no blocker is imposed on window4.
