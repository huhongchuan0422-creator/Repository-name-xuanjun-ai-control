# Three hosts: parallel preparation, separate acceptance

PR17 #6332994640. Parent9d85c157. SOURCE preparation only; no new host,
credential, service, catalog or production permission. The prior statement that
the domestic system interpreter path/hash was missing is superseded by the
original successful probe #6330641878. Do not repeat that successful probe.

## Domestic minimal shared authority first

Inherited exact system executable: /usr/bin/python3.11 root:root0755,15624B,
SHA256 d9d3833f98fe814c39497d1f05b48474cb214713dd32f3971a5f1877d548ec22;
RPM python3 3.11.6-30.alnx4 digest match; SOABI cpython-311-x86_64-linux-gnu;
SQLite3.42.0/OpenSSL3.0.12; glibc2.38/systemd255. Invoke t-sh070rht0th2lfk
Success/Exit0, raw498B SHA cf3f450fc6c59331add0972aca39c3fc12d26f04aed04ff0781e83afe304b25a.
This is not Certbot evidence and not an assumed system path.

Candidate isolated environment: /opt/xuanjun-cloud-oauth/venv-py3116, created only
from the exact system interpreter after explicit runtime-adoption confirmation.
No system-site-packages, no Certbot files/packages, no system-Python upgrade,
no PATH reliance. Original requirements.lock remains unchanged (18 packages).
Exact selected cp3116 Linux wheel hashes are produced from those allowed hashes;
ABI3 and py3-none-any are legitimate selected wheels, not all wheels say cp311.
The CI receipt records filenames, bytes, SHA, tags, Requires-Python and linkage.
CI uses the official Python3.11.6 bookworm image; it is an upstream compatibility
environment, NOT the domestic vendor RPM or its patch/OpenSSL/SQLite build.
A successful upstream run cannot claim a full domestic sandbox/ABI acceptance.
The original 29 HTTP cases cover deadlines, PKCE, refresh/revoke/replay,
concurrent identity isolation and SQLite restart; source/persistence regressions
are additionally run under exact3.11.6. No real GitHub login is mocked into PASS.

## Security patch evidence (public official sources, checked2026-10-22)

Alibaba Cloud Linux4 release notes:
https://help.aliyun.com/zh/alinux/product-overview/alibaba-cloud-linux-4-image-release-notes
The vendor explicitly lists python3.11 3.11.6-28.alnx4 ->3.11.6-30.alnx4
with fixes CVE-2026-7774 and CVE-2026-9669. This supports vendor backports:
version3.11.6 alone must not be equated to unpatched upstream3.11.6.
The installed package was reported as python3; source-package relationship and
complete current advisory coverage are not established by that version alone.
Do not infer all2026 advisories are fixed merely because release30 is present.

Python's official release page:
https://www.python.org/downloads/release/python-31117/
3.11 is security-fixes-only until October2027; upstream3.11.6 is superseded.
The historical3.11.6 test container is isolated test infrastructure, not a proposal
to deploy an unpatched upstream container. No security exemption is granted.
OpenSSL3.0.12/SQLite3.42.0 version strings likewise do not establish vendor RPM
patch releases. Reuse existing exact observations; if the remaining vendor-source
mapping/changelog and linked-library RPM releases are not in the original
records, request only that bounded non-secret package metadata before live
adoption. Do not re-run executable identity/version probes or scan directories.
ALAS main page returned a network error in this lookup, not a clean advisory bill.

## Startup and rollback delta (prepared, NOT applied)

Use the existing authority service NAME xuanjun-cloud-oauth.service, not a second
parallel service. New xuanjun-cloud-oauth-py3116.service.candidate differs from
the reviewed candidate only in ExecStart interpreter:
/opt/xuanjun-cloud-oauth/venv/bin/python ->
/opt/xuanjun-cloud-oauth/venv-py3116/bin/python.
-I -B, immutable run.py/current source, config/SHA, identity,18770 loopback,
ProtectHome, ProtectSystem, no capabilities, private state and limits remain.
No dependency on the failed domestic runtime archives; leave both files intact.

After applicable independent review and explicit adoption confirmation, the
sole execution owner must create the isolated venv with approved wheel selection,
verify pip check/imports/linked libraries and service-user sandbox visibility,
then apply the exact unit/config/Manifest binding. No commands here are live
permission. Source manifest changes require a new exact release; do not overwrite
the successful UK release or its Manifest. Keep initial catalogs empty.

Before a live switch, record the transaction's original unit/config/current/DB
state. For a first domestic deployment with no prior authority service, rollback
means stop only that new service and preserve DB/log/evidence; there is no invented
working3.12 service to restore. If a previous approved authority later exists,
restore its recorded exact unit/interpreter/source binding only after state and
schema compatibility are confirmed. Never empty the DB, replay unknown effects,
roll back shared Nginx/DNS/Certbot or restart successful UK installation steps.
Do not disable hardening to make imports work. Dependency/schema/source changes
still require affected-scope review, not an automatic runtime substitution.

## Independent host gates and original asset handoff

| Host | Inherited facts and preparation | Gate for its own acceptance |
| --- | --- | --- |
| Domestic minimal authority | Fixed host iZvt5t8tlrm8oiZ / cn-shanghai /3a22c458934142eea89ec6e3bf481a57; original machine role and read-only observations; issued cloud-auth certificate/bootstrap; Python/RPM facts above | Adopt exact runtime after compatibility/review; authorize actual account/config/DB/service changes and still-uncreated App/client secrets; limited TLS/peer evidence, original permit/Owner confirmation and real login/refresh/revoke/restart; introspect stays deny until source proof |
| UK resource | iZd7oeikknn1z21sq6ji6zZ /eu-west-1 /40dfc6a47d5e4363b9da7d0d6ab01cb1; successful3.12.15 runtime,18 deps and23-file release #6332421572 reused | Depends only on minimal domestic authority and its TLS/peer/client bindings, not all domestic business completion. New independent tunnel/App and actual OAuth consent/identity tests remain separate; preserve old connection and successful install |
| Korea business | iZmj7a5kwr75qc1tul4kf9Z /ap-northeast-2 /09207081a09a466aa0079b07b5e3e7ca; existing role/host/OS-file SHA/standing-executor acceptance inherited | Business catalog/root_ref, fixed operation, original project request/selected Manifest/budget and recipient mapping must be bound; no new Korea service, runtime, port or deployment guessed/started. Its acceptance can proceed as soon as its own complete binding exists |

Domestic business uses its original website PR122/customer-service records and
fixed action, separate from deploying shared authority. Website20-item collector
SHA c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f,
root/input/source and state constraints stay original; new localOS success is not
website state evidence. Domestic customer-service source snapshot SHA
 e5047757261a270cd9c5c4a3c8ac50057053bf546143275f713a1bb9eba5a489
is historical structure, not current data permission. No customer DB/token read.
Korea's Binance service and candidate business actions stay under their original
project scope; server access is not a trading or money-operation authorization.

B5 after UK authentication acceptance: original #6316275680/#6316439576/#6316671622
selection, full catalog, both root_ref mappings, recipient/object/operation and
16MiB project budget must still pass. Original manifest reference
cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba
and372-member4114893B known boundary are historical evidence, not a final selected
catalog. Node126595440B cannot be split to evade the budget. Do not install P2.

No three-host barrier: each host records SOURCE, HOSTED, LIVE and remaining gates
separately. This preparation does not assert that credentials, App, deployment,
project roots or newly registered operations already exist.
