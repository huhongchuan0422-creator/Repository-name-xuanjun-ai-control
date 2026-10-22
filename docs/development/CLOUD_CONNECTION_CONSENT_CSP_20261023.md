# Consent form callback CSP compatibility

## Scope
Base: 5fec3f7b6716a592a5176984d10d14d27f79cba8. Only a successful authenticated GET /consent HTML response gains one selected callback source alongside self. The source is reconstructed from a bounded query-free ASCII HTTPS callback after exact current-client registration matching. The global default, error responses, POST responses and all other security headers remain unchanged. No new grants, scopes, credentials, database schema or business roots.

## Security boundaries
CSP source strings reject wildcard, userinfo, whitespace, controls, query, fragment and policy separators. Valid registered callback URLs outside this deliberately narrow serialization profile fail closed. CSP redirect matching can ignore source paths, so the existing Authlib exact URI, client, resource, PKCE, CSRF and Owner checks remain mandatory and unchanged. This does not allow arbitrary destinations or remove CSP.

## Evidence and limits
Local pinned Flask/Authlib: 15 new boundary cases and 11 prior isolated integration cases passed, independently reviewed. Local independent Chromium launch failed with ProcessSingleton socket Operation not permitted before any page or form action. That browser run is NOT_EXECUTED and is not evidence of browser success or of the live incident root cause. Production OAuth has not been replayed by these tests. Hosted results must be checked for this exact new commit, including the new browser job, before claiming browser verification.

## Hosted-only browser test
The existing source-branch workflow gains one ubuntu-22.04 job, read-only repository permissions, no secrets, no self-hosted runners and no deployment commands. Four test-only official PyPI wheels are exact-version/hash locked for Python3.12 Linux x86_64; Playwright fetches its corresponding official Chromium. Chromium sandbox is explicitly enabled; no sandbox-disabling fallback is permitted. Failure to launch is a test failure, not a skip. The job is bounded to ten minutes and the test to sixty seconds.

Two ephemeral loopback HTTP servers and an isolated fresh browser profile exercise a synthetic form POST and 302 with no real OAuth parameters: the original self policy must block the other origin, the selected source must permit it, and a different origin must remain blocked. This is browser policy behavior, not TLS or live OAuth acceptance. Context routing rejects non-loopback destinations. No live GitHub/ChatGPT pages, cookies or credentials are used.

## Rollout
Source publication and Hosted tests are separate from production deployment. Do not modify the running 5fec release in place, reuse a consumed consent flow, extract authorization codes, or manually bypass a blocked browser redirect. A later approved rollout must preserve the prior release and use a new normal OAuth flow only after tests/review and deployment succeed.
