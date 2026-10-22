# OAuth recipient boundary — source candidate

Owner adoption: PR17 #6329261672. Parent candidate acf1c51ce7e73e30147ceabad51813556bb1a0ec.

This increment implements the resource-side authentication-to-transfer boundary,
not an authorization server or an installed HTTP endpoint. It introduces no
new scheduler, Writer, listener, service, permission, credential or cloud call.
The installed stdio MCP and its two registered tools are unchanged.

## Implemented source

`production/cloud_connection/oauth_resource.py` uses RFC7662 HTTPS POST
introspection with confidential client authentication. Endpoint/issuer/audience
and subject-to-recipient/project mapping come from host configuration, never
from tool arguments or `_meta`. Redirects and environment proxy inheritance are
disabled. TLS uses Python's normal verified HTTPS stack. Introspection responses
are bounded to16KiB and timeout5seconds; errors reveal no raw responses or secrets.

Every call rechecks active state, issuer, audience, time, bearer type, scope,
subject and project. No positive token cache delays revocation. The request-local
verified recipient enters the existing `ExistingProjectFiles` bridge, retaining
catalog, original SUCCESS/InvokeId, original budgets, path, size and SHA checks.
The adapter is disabled by default. Caller headers must be provided by a trusted
HTTP host; arbitrary Python callers are not a new security principal.

The issuer profile deliberately requires `iss`, `aud`, `iat`, `exp`, `sub`,
`scope`, and `token_type` in an active introspection response. These are stricter
deployment requirements than RFC7662's minimal response; the eventual standard
authorization server must be configured and tested for this profile. Missing
fields refuse access, not implicit approval.

## Tests and evidence limits

Offline tests exercise authenticated reads through real temporary files and the
original SQLite SUCCESS record fixture. Authorization records and issuer replies
are synthetic fixtures, not production approvals. Cases include revocation,
wrong scope/issuer/audience/subject/project, duplicate JSON keys, oversized and
invalid replies, failed secret retrieval, timeout/network failure, redirect,
untrusted identity parameters and disabled/unregistered catalogs.

No live login, real GitHub principal verification, token issuance, token refresh,
client registration, DNS/TLS change, transport reconfiguration or server file
transfer occurred. This is SOURCE candidate, not LIVE connection completion.

## Remaining concrete integration

1. Standard authorization service with GitHub identity verification, authorization
   code/S256PKCE, exact redirect registration, rotating/revocable refresh sessions
   and protected persistent state; no hand-written token issuer.
2. Protected OAuth HTTP resource host and discovery, request-local header binding,
   limits and no request/token logging. Install the host-owned mapping and catalog
   by the normal reviewed configuration path, not tool claims.
3. Independent review of changed source/configuration; then applicable live
   admission and Owner secure login/consent. Existing authorization for the chosen
   OAuth proposal need not be requested again.
4. Real project task/catalog readiness, successful object retrieval with two-end
   SHA, transport restart and real session refresh/revocation tests. OS-release
   success cannot substitute for project object authorization or acceptance.

The sealed second-window request remains sealed. This source increment does not
resubmit it or introduce a different path for that rejected operation. Existing
three-host connection results remain reusable; no installation or business
deployment is authorized by these tests.

Protocol reference: https://www.rfc-editor.org/rfc/rfc7662.html
