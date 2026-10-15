# PR122 minimal cutover review candidate

Reuses the current Domestic immutable static stage and existing Tokyo18080
backend. No new OAuth runtime, SQLite import, credentials transfer or service
rewrite. The original static RG1 package and its manifest remain unchanged;
these extra review files are NOT added to that approved package.

Origin: GitHub Tokyo non-root inventory run38764344743/job116523523247,
artifact11987296370. It directly collects current on-disk config as the
existing githubrunner user; no nginx -T, sudo or private-key read; any inline secret values in public
configuration are redacted in memory and never exported.
This is source configuration evidence, not proof Nginx loaded those bytes or a
production release. Owner earlier Nginx-T and direct TLS200 are separate facts.
75 locations:62 static,11 dynamic,1 ACME and1 default deny. Location count is
NOT the historical109-URL acceptance list. The exact/subpath aliases are
retained, including trailing slash/privacy/TikTok verification targets.

The domestic proxy uses fixed Tokyo47.245.53.152 over verified TLS with exact
SNI/Host. It forwards original paths/query/method/body and authentication,
cookies, Origin/CSRF and Telegram headers. No invented endpoint or broader
/submit prefix is exposed; only the original two submit routes are bridged.
Telegram remains checked by its original Tokyo Nginx nested controls. No bot
secret is embedded or copied. Trusted client-IP behavior is NOT proven: Tokyo
currently overwrites X-Real-IP with its own peer, which will become Domestic.
No application authorization is asserted to be independent of that change;
this semantic difference remains an explicit pre-release review/acceptance gate.

All upstream retries are OFF, including sensitive POST and OAuth callbacks;
upstream failures preserve non-success HTTP status. There is no caching,
request/response temp file storage or new static CSP on dynamic portal pages.
The status-only log excludes URI/query/body/headers/IP. Raw request-bearing
error logging is suppressed; this trades diagnostic detail for secret safety.
Operational status/error monitoring and acceptance remain pre-release gates.

The CA path is now bound to observed Domestic root-owned0444 system bundle
/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem (148 certificates), verified
by non-root run38765986129/job116529173285. Revalidate its identity and trust
state at installation; no verification disable or private-key transfer is used. No config installer/reload,
certbot invocation, DNS action, new root grant or merge is provided here.
Existing reviewed bootstrap/ACME/renewal assets stay separate and reusable.
Installing this candidate in addition to the old apex config would conflict;
W05/W06 must bind the exact config set/backups and prove no duplicate server.

Required rollback: preserve old exact config/current pointer/DNS before any
change. On failed pre-DNS validation keep old DNS; on failed cutover restore
approved DNS/config/pointer in the reviewed sequence. No blind replay of failed
sensitive requests. Tokyo remains running and authoritative for backend data.
This candidate never grants Tokyo retirement or claims all-server migration.

CI real-Nginx tests use a loopback HTTP frontend and a fake TLS upstream; they
prove routing/upstream TLS behavior, not the Domestic public443 certificate or
loaded production config. Those remain W05/W06 gates.

Read-only CA discovery history: first run38765774173 stopped because Python's
default cafile paths were absent (capath may still provide trust). No host change
or blind retry occurred. Corrected discovery checked the existing distro bundle
paths; run38765986129 passed. ACME public root already exists as root0755 and
is not a symlink. None of this issues a certificate or reloads Nginx.
