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

## Increment after independent review #6329897984

Review baseline146b0e35419204e7940c9927f35ecca30edd56a1. The three resource-side
clock/strict-enable/introspection-deadline fixes were independently closed and
are inherited. `oauth_resource.py` is unchanged in this increment. Only the
GitHub wire boundary, callback capacity, MCP initialize negotiation, affected
tests and this manifest/document are changed. Authlib version/protocol,
authorization DB/grants, queues/workers, live profiles and default-off examples
are not replaced.

A. `github_network.GithubApp/GithubSession` extend Authlib's documented client
classes and replace only Requests' wire send. Authlib retains state and S256PKCE
validation, token exchange/parsing and authentication. The whole callback's
token+user network chain shares one monotonic5-second deadline. Each fixed
request runs in a cancellable spawned process; DNS/connect/TLS/headers/body
are included. There is no per-stage budget reset. Cleanup is bounded separately
as in the independently accepted resource-side implementation. Both success and
failure close pipes and reap/terminate children. No exception/request/token body
is returned or logged on failure.

Only POST `https://github.com/login/oauth/access_token` and GET
`https://api.github.com/user` are permitted wire targets. No redirects, inherited
proxies, cookies or arbitrary request URL. Token bodies are bounded16KiB, user
bodies64KiB, including streamed bodies without Content-Length. Child-local HTTP
header limits are8KiB/line,32headers and16KiB aggregate before reading the body.
The normal verified TLS trust store is used. Offline tests inject only a
loopback TLS transport route/CA, never a principal or auth result; the production
host loader exposes no such configuration fields. Merely changing the obsolete
Authlib timeout keyword is not the fix.

At most2callback wire chains may run per authority app. Excess callbacks refuse
immediately before exchanging a code. The real service's4HTTP threads retain
capacity for introspection/revocation. The permit is released on every network
failure/success, not a persistent installation Attempt counter. Failures never
bind the flow subject or issue local codes. Existing expiry checks and SQL
single-use/atomicity continue to apply.

B. MCP initialize checks date-shaped string syntax. Supported versions echo
back; legal unknown versions negotiate `PROTOCOLS[-1]` (currently2025-06-18).
An initial valid unknown version header can negotiate as well. Subsequent
requests still reject unsupported protocol headers. Each request independently
authenticates; negotiation creates no shared principal/session authority.
Actual HTTP tests cover support/unknown fallback, invalid syntax, subsequent
supported/unsupported headers and an unauthenticated request after successful
initialize. This follows the existing stdio adapter's version strategy.

Additional actual TLS/HTTP negative cases cover both GitHub stages with slow
headers, drip and no response; declared/streamed oversized bodies, oversized
headers, redirects with a never-hit redirect sink, environment-proxy poisoning,
and combined3s+3s delays stopped by a single5s chain deadline. A four-slot HTTP
WSGI host exercises two blocked callbacks plus immediate overload rejection,
while introspection and revocation still complete; slots are then reusable.
It is a controlled four-slot test host, not a production Waitress benchmark.
The simulated GitHub provider and production live evidence remain separate.

## Existing-record binding reconciliation (no new server commands)

| Field | Evidence actually read | Exact conclusion |
| --- | --- | --- |
| GitHub App callback | This factory's fixed issuer + `/github/callback`; original Owner-approved design #6329261672 | Fixed design `https://cloud-auth.wenwenwenyiyiyi.work/github/callback`; not a registered/live App callback yet |
| ChatGPT OAuth callback | Existing original plugin receipt #6321045032 describes the two-tool stdio plugin, no OAuth registration/callback | Not established in the read records; retrieve exact URI from the same plugin's normal OAuth settings, not an example URL or Owner guess |
| Existing tunnel/plugin | #6320454963 and #6321045032 | Tunnel `tunnel_6ad8e1d2482c8191b542ba8dd38c3545`; plugin `plugin_asdk_app_6ad8e68b582881918fcfd3da6e5b65fd`; these identifiers are not a token audience |
| Actual audience/resource URI | The retrieved tunnel creation/plugin receipts give IDs and stdio operation, not a verified OAuth resource URI | Not established; obtain through the normal same-plugin/tunnel settings/discovery and bind both issuer and resource exactly; do not invent an HTTPS URL |
| UK original host compatibility | Original `CLOUD_CONNECTION_CONTINUATION_20261021.md` records actual host observation | Python3.6.8, SQLite3.26.0, systemd239 are inherited history; do not restate them as unknown or freshly measured |
| Modern UK container/interpreter | Original PR133 #6281322867 | `xuanjun-p2-sandbox:prep-base-20261013` is a known label, but that receipt explicitly leaves immutable digest and actual3.11 executable output unknown; no P2 launch or container approval inherited for OAuth |
| Modern dependency ABI | Pinned release metadata contains cryptography50.0.2 cp311/cp39 abi3 x86_64 wheels for manylinux2_17/2_28/2_34; hashes are already in the lock | Local/Hosted Bookworm installs are proven; do not infer all wheels require2_34, nor infer a real host interpreter/venv is usable without its own record |
| UK original credential/profile references | #6318348766/#6321045032 and the original source docs | `/etc/xuanjun-cloud-executor/credentials.json` and `openai-tunnel-runtime.key` remain existing private references, not OAuth secrets to copy; original unit/profile hashes and secret expiry2026-11-20 are inherited |
| New OAuth configuration | Existing candidate examples plus the fixed loader paths | Source templates only. No real config SHA, new secret, dedicated account, TLS certificate reference or service deployment has been created by this batch |

Remaining exact observations before requesting final live activation: normal
plugin's actual callback/resource URI; approved modern runtime executable and
dependency ABI per host; domestic systemd/version and the new dedicated
account's actual UID/GID; free fixed ports, exact approved certificate/renewal
references and UK outboundIP used by the Nginx allowlist; actual reviewed
configuration/source pins and project catalog/root references. Retrieve these
through existing authorized read-only records/UI/preflight, not public raw
credentials or broad scans. Historical matches are reused, not recollected.

The prior7-point change list is an enumerated design scope, not a request to
approve placeholder callback/audience/host values. No final live activation
request is issued with those fields unbound. Original resource-side3fixes,
unrelated accepted features and old production operations are not reopened.
After this source increment passes independent review, continue that precise
binding/admission phase; this is not overall long-term connection acceptance.

References for this increment:
https://raw.githubusercontent.com/authlib/authlib/v1.9.1/authlib/integrations/requests_client/oauth2_session.py
https://raw.githubusercontent.com/authlib/authlib/v1.9.1/authlib/integrations/base_client/sync_app.py
https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle


## Same-round Work deployment delta — #6330030281

This supersedes the earlier incomplete modern-container row above. Work's
original-record read supplies #6282808058: fixed image prefix5341f193,
Python3.11.2 at /usr/bin/python3.11,6809944bytes,
SHA256 9bee109da0dce17a7c9eeaca9f420cc6770a9fe143b9382d73bd22fe59b21a5f,
UID1002. Reuse that evidence without another request. The P2 container has
network=none; neither its network nor its role is changed for OAuth. It does
not prove that the candidate host /opt/xuanjun-cloud-oauth/venv/bin/python
exists or that the locked dependencies work there.

The existing ChatGPT plugin management UI was read during this round, without
editing, refreshing tools or creating credentials. App
asdk_app_6ad8e68b582881918fcfd3da6e5b65fd reports supported authorization=None
and used authorization=None; current version
asdk_app_v_6ad8e68b582c8191a9f3586713868d44, DEVELOPMENT. That management surface
shows no OAuth callback or resource audience. This is evidence about this
registration, not a claim that the platform cannot support OAuth. Registration
must use the normal supported OAuth path; IDs cannot stand in for callback or
audience, and no placeholder values are approved.

The original activation checklist is retained, with these exact open facts:

| Item | Reused fact | Required binding before activation |
| --- | --- | --- |
| Runtime | UK systemd239; old host Python3.6.8/SQLite3.26.0; fixed P2 container3.11.2 above | Host candidate executable/venv, architecture/glibc and locked wheel compatibility; domestic interpreter/systemd facts; no host upgrade or P2 repurposing implied |
| Ports and network | UK127.0.0.1:18769/mcp and domestic127.0.0.1:18770 are fixed candidate listeners | Existing occupancy/binding evidence for those two ports, actual UK outbound source; old28443 SSH forward is unrelated; template allow8.208.119.115 is not proven egress |
| TLS | Proposed cloud-auth.wenwenwenyiyiyi.work and /etc/xuanjun-cloud-oauth/tls-approved.conf | Non-secret certificate reference, domain coverage, expiry/renewal owner and exact Nginx include; website TLS does not establish this subdomain |
| Identity | GitHub callback design /github/callback; current ChatGPT registration auth=None | Real App callback registration, exact ChatGPT OAuth callback, common protected-resource audience, subject/recipient/project map and protected config SHA |
| Catalog and roots | #6329200842/#6329032582; catalog6919B SHA62b1eef3a48b004c2b426cfff1ee7489af0eecaecdc80d4953479b7b581f2689; selected_members=[]; CANDIDATE_BLOCKED_NOT_DISPATCHABLE | Approved source_root_ref/recipient_root_ref, selection, original SUCCESS/fetch_approved_object/InvokeId and recipient binding; no OS-result or fixture substitution |
| Mount visibility | Candidate resource unit ProtectHome=yes, ProtectSystem=strict, empty CapabilityBoundingSet and explicit credential denials remain unchanged | For each approved resolved root: ancestry, UID/GID/mode, mount visibility and read/traverse access under the exact unit restrictions; /home,/root,/run/user are hidden, /var/lib is outside ProtectHome but access is still not proven |

The historical B5 source snapshot under
/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002 is outside
ProtectHome's hidden trees. Its historical hashes do not grant transport or
prove current visibility. Empty capabilities also mean root cannot be assumed
to bypass ordinary file permissions. No actual catalog roots are approved yet;
therefore no root is marked readable merely because it is outside /home.
If an approved root conflicts with sandbox visibility, propose only a precisely
scoped read-only mapping with its own reviewed configuration; do not delete
ProtectHome or open an ancestor tree to make it run. No such mapping is
implemented or authorized by this document.

Original B5 budget16MiB remains; the Node126595440byte overage is not waived or
split into small requests. Website fixed20-item inputs/source references and
host mapping remain as recorded in #6329032582/#6320420824, not guessed.

All observations in Work's receipt are historical reads, not fresh server
checks. This round performs no server commands, deployment, account/App/secret
creation, network changes, tool refresh or permission edits. The table is the
single concentrated fact/activation delta, not a request for blanket approval.
