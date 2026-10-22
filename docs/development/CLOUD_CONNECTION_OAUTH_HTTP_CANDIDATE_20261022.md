# Complete OAuth / HTTP source candidate — not enrolled

Owner task: PR17 #6329401985 and subsequent explicit request to complete standard
OAuth plus real HTTP, retaining the existing queue and worker. Parent source:
c3f30bd8e3077f7aa4c0d21a05c8adfa9f180b26. This document supersedes the earlier
resource-only implementation status, not its historical test results.

## Actual implementation and boundaries

Authlib1.9.1 implements authorization-code exchange, S256PKCE, opaque access and
refresh token generation, introspection and revocation. Flask3.1.2/Waitress3.0.2
host the applications. All18 direct/transitive dependencies and distribution
hashes are in `deployment/cloud-connection/oauth/requirements.lock`. Modern
Python3.11/3.12 is isolated from the existing legacy Python3.6 worker. There is no
model API, hand-written JWT issuer, replacement queue, execution worker or shell
tool in this component.

`oauth_authority.create_app` registers real standard endpoints, exact callback
allowlists, explicit resource binding, S256-only authorization, GitHub's actual
OAuth/token/user endpoints through Authlib, and an explicit consent+CSRF flow.
Only verified numeric GitHub identities332398908/95597695 can become local
subjects. Model arguments, display names, cookies without a signature, tunnel
workspace, `_meta` and file catalog cannot establish identity. No GitHub token
is saved to cookie, database, repository or audit output; it exists in the
callback's request context to fetch identity. The minimal GitHub login requests
no repository/email/write scopes. This does not reuse the connector's token.

Browser flows expire in600seconds, authorization codes in120seconds, access
tokens in900seconds. Refresh families have an absolute7-day lifetime; successful
rotation revokes the old access/refresh credential. Replay revokes successors in
the same family, never creates extra credentials. Codes and tokens are stored as
SHA256 hashes. The pre-existing dedicated authority SQLite database is opened
with `mode=rw`, never silently created by the service. Explicit first-time
schema bootstrap is a separately admitted deployment step. Schema errors and
unknown/corrupt state HOLD. This authority database is new authentication state,
not a substitute for any project, queue, P2 or transaction history.

Grant validation, read, insertion, single-use consumption and COMMIT run in one
BEGIN IMMEDIATE transaction. Busy/COMMIT failure rolls back without returning
issued tokens. Nested caller transactions are rejected, not committed. DB
connections are request-local. No automatic retry occurs. Expired or revoked
records are retained, not reset. Pending browser flows are bounded128 and total
flow history100000; exhaustion HOLDs for normal maintenance, not blind deletion.

`oauth_http.create_resource_app` is a stateless JSON Streamable HTTP MCP endpoint
at `/mcp`, with protected-resource discovery, 401 Bearer challenge, bounded JSON,
duplicate-key rejection and actual Authorization-header binding. The entrypoint
binds only UK127.0.0.1:18769. It retains original status/approvedOS tools and adds
only read_project_chunk. Project reads require the host-approved catalog,
original SUCCESS task/InvokeId, original recipient/project/budgets, descriptor
path checks and SHA; arbitrary paths, execution and task submission are absent.
Origins and query-string credentials are refused. No mutable shared current user
or MCP session state can transfer authorization between callers.

Introspection performs a fixed HTTPS POST, refuses redirects/proxy inheritance,
and bounds16KiB. A cancellable spawned process plus the parent's monotonic
deadline bounds DNS/connect/TLS/headers/body together; drip traffic cannot reset
the5-second network budget. On expiry the network child is terminated and
reaped; up to0.2seconds bounded process cleanup is separate from the network
deadline. Before granting, wall clock is sampled again after the response; expiry,
clock rollback/non-finite values and elapsed deadline refuse. `enabled` must be
the literal Boolean true everywhere. Production does not install test transports.

## Real tests versus LIVE

Integration tests start actual local TLS/HTTP servers, use the real Authlib code,
real browser redirect/cookie/CSRF flow, SQLite files/multiple connections and the
original transfer/receiver. GitHub's upstream is an explicitly simulated HTTP
provider; no app authentication function is replaced with a fixture principal.
The test transport rewrite exists only in tests. Tests cover code exchange,
wrong PKCE/callback/resource, scope escalation, rotation/replay/revocation,
concurrent exchange/refresh, COMMIT BUSY rollback, fixed catalog transfer and
actual two-end whole-file SHA, cross-subject/project isolation, missing state,
expiry, real slow HTTPS drip cancellation, and independent authority process
restart with persistent refresh/revocation. Original SUCCESS/approval records in
the transfer fixture remain synthetic and are never installation authorization.

Real GitHub login, cloud-auth DNS/TLS, existing tunnel HTTP upstream, plugin OAuth
registration, production project object retrieval and platform credential
renewal are NOT_EXECUTED. Systemd candidates are not installed or host-validated.
The factory/entrypoint and both configuration examples are default-disabled.
The original worker, stdio profile, queue and online tools remain unchanged.

## Exact deployment candidate and single change confirmation list

These changes require independent review and applicable live admission. Owner's
choice of OAuth is already authorized; do not ask to choose OAuth again. Before
live changes present this complete list once, filling the platform-generated
callback and environment facts by normal read-only UI/preflight, not guessing:

1. Project-specific GitHub OAuth App with sole callback
   `https://cloud-auth.wenwenwenyiyiyi.work/github/callback`; no repo/write scopes.
   Create and privately retain its client secret. Register one ChatGPT client
   with its exact platform-provided HTTPS callback URI, and one confidential
   resource introspection client. No wildcard/default callback or arbitrary
   dynamic registration. ClientID/callback is non-secret; secrets never public.
2. Domestic dedicated system account/group `xuanjun_oauth`, no login/sudo, for
   `xuanjun-cloud-oauth.service`, loopback127.0.0.1:18770. This account does not yet
   exist or have authorization merely because a template names it. Root installs
   immutable source; the account owns only its private auth state and runtime
   secret files. No permission over cloud credentials or project execution.
3. Protected configuration/secret namespace `/etc/xuanjun-cloud-oauth/`, private
   state `/var/lib/xuanjun-cloud-oauth/authority.sqlite` and immutable code under
   `/opt/xuanjun-cloud-oauth/`. Four separate secret purposes: GitHub client,
   ChatGPT confidential client, resource introspection, and browser session
   signing. Secret file0600/single-link; state directory0700. Config+source
   manifest hashes are pinned in the root-installed service environment. No
   secret is passed via command arguments, URL or public artifacts.
4. DNS/TLS for `cloud-auth.wenwenwenyiyiyi.work` on the existing domestic host;
   a dedicated reverse-proxy vhost forwarding only this authority, fixed Host,
   stripped untrusted forwarding headers, TLS renewal, body/rate limits, and no
   query/body/Authorization logging. Existing website vhosts are preserved.
5. UK `xuanjun-cloud-oauth-resource.service`, root only for the original protected
   read-only adapter, loopback127.0.0.1:18769. No capabilities or writable state
   mounts. Root configuration is under `/etc/xuanjun-cloud-executor/`; same
   private queue/approved result roots, no new queue/worker. Catalog roots remain
   empty until exact project catalogs/roots/budgets are admitted. No arbitrary
   home-directory access is granted by the template.
6. Update only the original tunnel's upstream from pinned stdio to
   `http://127.0.0.1:18769/mcp`, preserving its existing Read/Use key, workspace,
   expiry and restrictions. Configure the same plugin's standard OAuth fields
   through the normal settings UI. Record the actual protected-resource URL as
   audience in BOTH services; it is currently unknown, not a fabricated URL.
   No new tunnel, scope escalation or sealed task resubmission.
7. Confirm a compatible isolated modern interpreter/runtime on each host.
   Locked binary wheels are tested on Linux x86_64 Bookworm, not old host glibc.
   Reuse an approved modern runtime if available; do not upgrade system Python,
   start old P2/B5, download runtimes or change isolation without the exact
   admission. Candidate unit hardening flags must be checked against the real
   systemd version before installation, not silently dropped.

## Activation, evidence and rollback

Freeze actual issuer, audience, callbacks, config hashes, approved catalogs/root
references and SOURCE_MANIFEST, and complete independent review. Before the
single admitted activation, back up only the existing tunnel/profile/unit
metadata and preserve the original pinned stdio release and result queue.
Check the two loopback ports and exact host/service identities; do not sweep
the filesystem or read client data. Install the reviewed isolated source and
private auth state by the normal granted path. The bootstrap must refuse an
existing DB, not overwrite it. Do not change unrelated services or permissions.

Enable the two reviewed services only after required confirmation. Verify
issuer/resource discovery and unauthenticated401 first, then Owner completes
real GitHub login/consent through secure UI. Verify actual verified subject and
scope, an admitted project file's source+recipient SHA, wrong-recipient denial,
refresh/revocation and service/tunnel restart. Keep queue/InvokeId and private
receipt references; never publish tokens or project bytes. Stop on UNKNOWN,
wrong target, identity mismatch, expired credentials or failed SHA. Successful
old project stages are not replayed. Remaining B5 catalog closure and project
host mappings are independent project prerequisites, not OAuth identity.

Rollback changes only this new component: stop the new OAuth services, restore
the recorded original tunnel/profile/stdin source pin, revoke the new client
refresh families/app credentials through the normal authenticated mechanism,
and retain auth DB/logs/queue/transfer history. Do not delete/reinitialize state,
revoke existing cloud RAM/SSH, reinstall a business project, or replay sealed
requests. Partial/unknown changes require trusted status reconciliation before
any restart or repeated write.

Primary sources: https://docs.authlib.org/en/stable/oauth2/authorization-server/flask/authorization-server.html
https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
https://developers.openai.com/plugins/build/auth
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
