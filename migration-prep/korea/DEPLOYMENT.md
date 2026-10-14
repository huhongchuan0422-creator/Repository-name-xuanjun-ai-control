# Korea isolated deployment candidate

This directory is packaging input only. Nothing here installs a user, directory,
service, SecretRef, firewall rule, credential, or Writer.

The candidate uses its own Python 3.11 virtual environment and dedicated service
identity. The systemd template keeps release/config read-only and state/log roots
writable. A destination firewall may restrict Binance HTTPS destinations, but it
cannot inspect the encrypted HTTP method. Therefore `get_only_policy.py` is the
mandatory application-layer method/path guard; the root egress policy remains a
separate deployment prerequisite.

Shadow acceptance requires a minimum 24-hour run, zero decision/position/order/
protective mismatches, zero unknown/in-flight state, and restart recovery. These
thresholds are candidate defaults and still need Owner approval. The canary in this
artifact permits zero new entries because no production Writer authority is packaged.

Rollback is Korea-first: lock Korea Writer, revoke its credential, remove its IP,
reconcile every unknown outcome, and only then consider Tokyo restoration and a new
Tokyo epoch. Yibi, novel, PostgreSQL, Redis and either production Runner are outside
this artifact and must remain unchanged.
