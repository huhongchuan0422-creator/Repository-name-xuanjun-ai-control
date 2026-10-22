# Pre-egress HTTPS and domestic runtime increment

Original PR17 #6332775422; source parent d866f69. Preserve the original 211+7
cases, UK runtime/dependencies/source, DNS, bootstrap and issued certificate.
This change prepares configuration and tests only. It does not enroll a new
service, listener, credential, project catalog or transport root.

The exact 1276-byte pre-egress vhost replaces only the old introspect allowlist
and proxy include with `return 403`. GET, POST, queries and forwarded headers must
not reach any upstream. The TLS include binds only the new issued lineage.
Actual domestic syntax check #6332662573 is inherited; behavioral tests here use
isolated loopback Nginx, ephemeral test certificates and a counted synthetic
upstream. Test TLS bypass applies only to the generated local certificate.
Hosted requires real Nginx; missing binaries cannot produce a PASS.

## Observation preparation and withdrawal

The two templates are inserted into the new vhost's http and TLS-server contexts
only after applicable review/admission. Render one nonce of exactly 64 lowercase
hex characters; bind the owning transaction, host and UTC start. Replace
SECONDS_PATTERN with exactly the 60 consecutive integer epoch seconds beginning
at that approved start, joined with `|`. Replace PRIVATE_LOG with the exact
approved root-private log path, never a request parameter. Refuse unresolved
placeholders, invalid inputs, an existing conflicting log/config or an unverified
original TCP peer variable. Never change global real_ip settings.

Nginx's `$msec` map fails closed outside those seconds (410); process restart does
not refresh the window. Only the exact nonce URI accepts GET with no query (204).
Other methods return405 and queries400. The JSON line contains only nonce, UTC epoch seconds (`$msec`, independent of host timezone),
original TCP peer `$realip_remote_addr`, method and status. Forwarded headers,
credentials, query values and body are not recorded. `introspect` remains403.
No request is sent to the application by this observation location.

After the one approved UK request, remove only the transaction's observation
location, map and log-format bindings, test configuration and reload by the
approved path. Verify the exact URI now404 and further requests do not append to
the log. Retain private log/SHA and withdrawal receipt; do not delete old logs,
certificate or account state. Failed withdrawal stops subsequent activation.
A clock rollback into the approved epoch window could make the map active again
until physical withdrawal; the external controller must treat clock uncertainty
as HOLD. The map alone is not an exactly-once ledger.
Read at most64KiB for evidence; oversized/multiple/ambiguous observations HOLD.
This is a read bound, not a physical log-size cap. No observation is enabled live
by this source change. Tests exercise active, expired and withdrawn configurations;
they are not domestic production egress evidence.

## Same artifact transfer assessment

Verified UK source object:
/opt/xuanjun-cloud-oauth/runtimes/cpython-3.12.15-20261021/runtime.tar.gz
34479606 bytes; SHA256
6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772.
The archive was preserved after the successful original install. Do not redownload
or re-execute that successful UK stage.

The deployed public queue/worker supports only probe/fetch_os_release; its
34MiB arbitrary binary upload/download is not enrolled. The candidate private
transfer requires authenticated recipient, approved project catalog, root_ref,
original successful object task/InvokeId and project budget. Runtime has no such
approved object binding in the inspected records. Initial OAuth catalog is empty.
The original B5 budget/selection cannot authorize or be raised for this archive.
Cloud RunCommand is a command channel, not an already-approved binary custody
protocol; do not invent thousands of chunk commands or expose an HTTP mirror.
No applicable verified same-artifact UK-to-domestic route is established by these
sources. This is a specific transfer gap, not a statement that cloud identities
or all server access are missing. No new destination/root/key/store is created.

If a normal existing approved file channel is produced, bind the fixed source
above and a new non-overwriting domestic archive destination within the approved
OAuth runtime root, per-file/total budget>=34479606, recipient/host, whole SHA,
write custody and failure reconciliation before invoking it. Recompute both ends;
only a full pinned archive can be extracted. Preserve both failed domestic files.

## Independent Python3.11.6 alternative: plan, not adoption

Correction from PR17 #6330641878/#6332994640 (no repeated host probe):
/usr/bin/python3.11 is root:root0755,15624 bytes, SHA256
d9d3833f98fe814c39497d1f05b48474cb214713dd32f3971a5f1877d548ec22.
RPM python3 3.11.6-30.alnx4 digest matches. Invoke t-sh070rht0th2lfk
Success/Exit0 confirmed CPython3.11.6, cpython-311-x86_64-linux-gnu,
SQLite3.42.0 and OpenSSL3.0.12; raw498 bytes SHA256
cf3f450fc6c59331add0972aca39c3fc12d26f04aed04ff0781e83afe304b25a.
These are verified inherited facts, not missing interpreter evidence.
Do not use or modify /opt/certbot or its packages.

Required alternative binding before adoption:
1. Reuse the exact interpreter/ABI/linkage evidence above. Dependency RPM release
and patch coverage beyond that original bounded probe remain separate facts; do
not re-collect successful interpreter identity/hash/version checks.
2. Separate /opt/xuanjun-cloud-oauth/venv-py3116 and the original hash-locked18
package selection, wheel tags and `pip check`; retain the3.12.15 requirement lock.
Thecp312 wheel hashes cannot provecp311 selection: record actual chosen wheels.
3. Run the affected OAuth/HTTP network-deadline, PKCE, rotation/revocation,
SQLite concurrency/restart and isolation tests under exactly3.11.6; existing
3.11.14 or3.12.15 Hosted runs are not substitute evidence. Pin a trusted available
3.11.6 test image/digest or verified build before claiming exact-version CI.
4. Review the patch-level/security/support difference from3.12.15 and compatibility
results, then explicitly update the runtime binding/deployment and rollback plan.
No silent downgrade, system-Python upgrade, shared environment edits or reuse of
an old permit under a new runtime. UNKNOWN remains HOLD.

Current alternative status: EXACT_UPSTREAM_3116_COMPATIBILITY_PASS / NOT_ADOPTED.
Run39725084091/job119647031445 actually installed the18 exact wheels and passed
29 HTTP plus187 source/persistence cases (8 Nginx skips); final frozen selection
and vendor/live boundaries are in CLOUD_CONNECTION_THREE_HOST_READINESS_20261022.md.
The two GitHub network timeouts are retained; no repeated same download or
production changes.
