# Korea isolated deployment candidate

This directory is packaging input only. Nothing here installs a user, directory,
service, SecretRef, firewall rule, credential, or Writer.

The candidate uses its own Python 3.11 virtual environment and dedicated service
identity. The systemd template keeps release/config read-only and state/log roots
writable. `ControlledHttpsTransport` is the only packaged HTTP transport: it has no
generic method API, ignores proxy environment variables through raw sockets, denies
redirects, pins resolved addresses, and requires normal TLS hostname/certificate
verification. The service template defaults egress to deny and requires a root-owned
expanded `@BINANCE_PINNED_IP_ALLOWLIST@` before it can be installed.

This still does not prove root-controlled egress or absence of every bypass in an
installed runtime. A destination firewall cannot inspect an encrypted HTTP method;
application GET enforcement and root network confinement are both mandatory and
must be independently audited after installation. No IP, unit or transport was
installed or exercised against Binance in this batch.

Shadow acceptance requires a minimum 24-hour run, zero decision/position/order/
protective mismatches, zero unknown/in-flight state, and restart recovery. These
thresholds are candidate defaults and still need Owner approval. The canary in this
artifact permits zero new entries because no production Writer authority is packaged.

Rollback is Korea-first: lock Korea Writer, revoke its credential, remove its IP,
reconcile every unknown outcome, and only then consider Tokyo restoration and a new
Tokyo epoch. Yibi, novel, PostgreSQL, Redis and either production Runner are outside
this artifact and must remain unchanged.
