# PR122 consolidated minimum website release sequence — REVIEW ONLY

This is the complete preparation sequence for the minimum website cutover, not
an installation receipt or authority to retire Tokyo. Owner authorizes pursuing
migration; existing independent review and exact release gates still apply.
No website source extraction/rebuild/install or current-pointer change is needed.
Use actual Tokyo/ Domestic server file evidence, not repository website copies.

## Exact reused assets and new assets

Use deploy/pr122-domestic-website/tls/{issue-apex-certificate.sh,
renew-apex-certificate.sh,xuanjun-apex-nginx-deploy-hook.sh} and its two
systemd/xuanjun-apex-cert-renew.{service,timer} unchanged. Bind their actual
GitHub bytes in REVIEW_BINDING; do not copy from an unknown host version.
Use the three HTTP candidates in this folder and existing HTTPS/proxy config.
Do NOT install pr122-dynamic-hold.locations.conf or an old apex HTTPS template:
they would substitute 503 or duplicate the current candidate server.
Never copy a TLS private key from Tokyo or upload it as an artifact.

## 1. Capture and pin before root writes

Recheck exact hostname, package binding, current pointer and current public
file manifest (1187 entries) against server-content-evidence.json. Original
Tokyo1187/11090003; Domestic1187/11090700, only approved TikTok JS differs.
Revalidate relevant Nginx config files and loaded nginx -T under root without
exporting inline secrets, public CA identity, host clock, ownership and free disk.
Capture root-private backups of exact affected Nginx config, renewal files and
unit state and apex DNS A/AAAA/TTL/proxy settings. Record names, hashes, modes,
previous absence and rollback path. Existing winctl/IP/WeCom files are excluded
from edits. Stop on any drift, existing apex certificate/config or unknown path;
never overwrite a newly discovered server block or certificate lineage.
No new sudo rules, keys, OpenClaw or UK/P2 activation.

## 2. HTTP-01 before changing DNS

Install only Domestic bootstrap apex port80 candidate; nginx -t then controlled
reload. Verify public47.101.152.210:80 with Host=apex serves a random temporary
public challenge object byte-for-byte and all non-challenge paths return503.
Install only Tokyo apex port80 ACME candidate AFTER verifying no exact apex
port80 block already exists. No edit to Tokyo443/location/root/current is needed.
nginx -t then controlled reload. Verify public DNS apex HTTP challenge reaches
the same Domestic random object through Tokyo; check A AND AAAA paths used by
ACME. On failure keep DNS unchanged, preserve logs and rollback only these
new configs. Remove only the exact temporary challenge object after verification.
HTTP challenge content is public, not credentials. Do not print secret-bearing
Nginx-T output. Existing public access to port80 remains a prerequisite.

## 3. Issue and configure renewal

Run unchanged issue-apex-certificate.sh with --release-gate-approved and the
Owner-approved existing ACME contact email (no guessed/new account identity).
Certificate issuance is an external mutation and requires the reviewed exact
release scope. Verify SAN=wenwenwenyiyiyi.work, validity, chain and private-key
owner/mode locally; no private bytes in logs. Keep winctl/IP lineages untouched.
Install unchanged renewal script/hook at their existing reviewed /usr/local/libexec
names, root-owned0755; install the two unchanged apex renewal units root0644.
Do not enable timer until HTTPS config is loaded and certbot renew --cert-name
wenwenwenyiyiyi.work --dry-run succeeds. Verify hook nginx-t failure cannot
reload; exercise hook only in approved acceptance and record actual service
reload outcome. Check existing general certbot scheduling for duplicate apex
renewal before activating a second scheduler; select one effective scheduler.
Record next run and recurrence receipt. Do not claim dry-run executes a deploy
hook unless tested explicitly (Certbot may not run deploy hooks on dry-run).

## 4. Install only minimum HTTPS configuration

Stage new root-owned configs in /etc/nginx/pr122-minimal-cutover with strict
path-chain checks. Add http-support.conf exactly once in http context before
apex HTTPS (log format must precede use); install apex-https.conf exactly once
as the Domestic443 server. Never blindly replace nginx.conf or all conf.d.
Use observed Domestic CA /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem;
verify system trust and root ownership, no ssl_verify off. nginx-t before reload.
On failed reload preserve evidence; inspect loaded/unknown outcome before any
retry. Restore prior exact configs only if their identity still matches this
transaction. Leave source website/current, shared bridge and Tokyo backend alone.

## 5. Real pre-DNS acceptance

Use curl --resolve wenwenwenyiyiyi.work:443:47.101.152.210 WITHOUT -k and
verify certificate, Host/SNI, bytes, headers/CSP, all109 historical acceptance
URLs,62 static rules and11 dynamic responsibilities. Do not substitute location
count or fake-CI samples for109 actual URLs. Exact historical109 URL list must
be located/bound before this gate passes; absence remains a blocker.
Read-only health/negative endpoint tests may be automated; never send customer
messages, credentials, live OAuth grants, payment writes or real business POSTs
as an unapproved smoke test. Verify authentication/denial behavior, callback
Host/Origin/cookie handling and original-client-IP implications at Tokyo.
Tokyo peer becomes Domestic and may affect auth/rate limits/audit; do not declare
that acceptable without evidence/explicit release decision. Existing nested
Telegram controls stay on Tokyo. Inspect existing winctl/WeCom unaffected.
Finally replace ONLY Domestic bootstrap file with domestic-apex-http-final.conf;
nginx-t/reload and repeat HTTP challenge+HTTPS redirect+TLS checks.

## 6. Single production release gate and DNS

Submit exact source/config/archive/CI, server baseline, root transaction receipts,
certificate+renewal and actual route acceptance together. Developer cannot
self-approve independent review. Before DNS change read exact apex A/AAAA/TTL/
proxy settings and authoritative current values; do not re-request12 DNS records.
Change only approved apex record(s) to Domestic47.101.152.210; preserve mail,
center,winctl,wecom,uk. Unresolved apex AAAA/other origin paths block cutover.
Verify authoritative readback, public HTTPS and deep routes from independent
networks. Proposed observation is24h; finalize interval in release decision.

## 7. Rollback and close

Pre-DNS failure: leave apex DNS on Tokyo; restore only transaction-owned Nginx
files to their recorded former bytes/absence, nginx-t/reload with known result.
Do not delete certificates, private state, receipts or original website files.
Post-DNS failure: restore recorded apex DNS values/proxy/TTL first while Tokyo
remains healthy, confirm public routing recovery; then restore only Domestic
transaction-owned config if required. Existing staged content/current is retained.
Never retry uncertain sensitive requests or replay callback/submit bodies.
Record production receipt with exact package/config hashes, issued cert fingerprint,
Nginx test/reload outcome, DNS old/new, route evidence, observation and rollback.
Website entrance can close only when all these pass. Tokyo18080 continues to
serve dynamic routes; full server migration S01-S12 is a separate incomplete
chain (portal/data/secrets, bridge/tunnel, Telegram/WeCom/Novel, PR99 Finance,
timers/control and final no-Tokyo-dependency/retirement). This packet does not
pretend those services are moved and never stops Tokyo or alters trading state.
