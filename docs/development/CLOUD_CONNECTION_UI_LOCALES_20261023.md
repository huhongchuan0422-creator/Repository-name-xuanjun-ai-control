# Optional OAuth ui_locales compatibility

## Scope and provenance

This is the existing CLOUD_CONNECTION_OAUTH_HTTP_ACTIVATION continuation, recorded through PR17. The source branch remains feature/cloud-connection-continuation-20261021. The submitted parent is 3c3f7afd2534c5be49c4155dc9dafd9a3c0ff8b6; its deployed product bytes still match 0177d3917278c6f243363d7fcb5a18c638dabd51. This is not a B5/P2 change or a change to PR17's unrelated head branch.

A normal platform authorization request included optional ui_locales. The original /authorize parameter-name allowlist rejected it with 400 before Authlib. No captured authorization URL, state, challenge, credential, or token is included here.

## Exact change

Only ui_locales is added to that allowlist. If present, its value must contain 1–128 ASCII characters, at most eight space-separated language-tag-shaped strings, and match the explicit letter/alphanumeric/hyphen grammar. This is bounded syntax validation, not complete BCP47 validation or locale negotiation. The display hint is ignored and removed before flow parameters are stored.

Duplicate query parameters, unknown names, HTTPS/Host, exact client/callback/resource, response type, S256 PKCE, state, scope, enrolled subject, consent and all token checks remain unchanged. No new authentication method, client, credential, scope or permission is introduced. The existing 30-member SOURCE_MANIFEST changes only the authority member's bytes and SHA256; dependency locks and schema are unchanged.

## Verification and limits

Before repository integration, 14 AST-isolated regressions and 11 real Flask/Authlib test_client tests were independently rerun successfully. Original0177 rejects a valid request plus ui_locales; the candidate reaches the unchanged /login next stage. Synthetic in-memory SQLite and a socket.connect prohibition were used. The local interpreter was CPython3.12.14 with original hash-locked Flask3.1.2/Authlib1.9.1 and dependencies fetched from official PyPI into a disposable local directory, not global site-packages.

The repository test tests/oauth/test_oauth_ui_locales.py contains ten real-factory tests, using normal production imports, no stored historical source fixture or external local path. It covers absence/presence, exact maximum bounds, invalid/non-ASCII/oversized hints, duplicate/unknown parameters and real Authlib client/callback/scope failures, plus resource/PKCE/Host/HTTPS boundaries. It does not follow /login and asserts zero socket.connect calls.

The existing cloud-connection-tests workflow already discovers these tests under its exact3.11.6 and other OAuth matrix environments. No workflow is changed and no server/self-hosted workflow is requested. Hosted results must be recorded for the new exact commit separately; old successful runs are not reused as this patch's CI result.

## Deployment boundary

This source change does not deploy or modify the running0177 release, database, configuration, keys, Nginx, units, autostart, old connection or UK resource/tunnel. After exact new source/manifest and applicable CI are checked, a separately controlled immutable domestic release and reversible current/env binding change can be prepared. Do not hot-edit0177, recreate the database, or replay an old captured authorization URL. A later fresh normal platform login must validate the real full chain; local /login redirection is not OAuth completion.

Registry integration also corrects the existing section references from 2/6 to the actual heading prefixes 2./6.; this does not change the compliance checker or any acceptance rule. The local full offline suite cannot run normally because its original fixtures require /root, absent in this restricted executor (195 discovered, 127 fixture errors, eight Nginx-dependent skips). It is not reported as passed and its source is not changed to mask this environment limit; the unchanged Hosted jobs provide that validation for the new commit.
