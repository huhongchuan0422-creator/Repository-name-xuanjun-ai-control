# UK Owner workbench deployment candidate

This directory is a candidate only. It does not authorize deployment or a
formal Telegram webhook change.

1. Freeze one reviewed commit and stage its exact files outside the repository.
2. Create the dedicated `xuanjun-callback` identity and shared DB-only group;
   it must not belong to `xuanjun_dev`, Docker, sudo or trading groups. Provision
   the dashboard bearer token, callback bearer token, callback HMAC
   key, Owner user ID and Owner private-chat ID as separate mode `0600` files.
   Never put their values in Git, systemd environment lines or logs. Callback
   secrets live only below `/etc/xuanjun-owner-callback`; its sole writable path
   is `/var/lib/xuanjun-owner-callback/state`.
3. Use only the manifest-bound renderer at
   `/opt/xuanjun-control-releases/<exact-release-directory>/scripts/uk-owner-workbench-config.py`;
   verify its recorded SHA-256, root ownership and `0555` mode before invoking
   it with `--owner-host`, `--tls-cert`, `--tls-key`, and `--verify-files`.
   Install the rendered `nginx.conf.template` output through the existing
   platform release gate, then run `nginx -t` before reloading nginx. Existing
   unrelated server blocks must be preserved.
4. Install the callback unit and the existing dashboard unit only after their
   source manifests match the frozen commit. Both application listeners remain
   loopback-only; only nginx listens on HTTPS.
5. Before activation run `callback_schema_gate.py` against the stopped or
   single-writer-gated database. It creates a consistent backup, migrates only a
   staged restore, validates the schema, and reports `live_switched=false`.
   Failure means zero switch. Activation of the staged DB is a later Release
   Gate action and is not performed by this candidate.
6. Acceptance requires external HTTPS checks for authorized and unauthorized
   dashboard reads, the complete `WAITING_HUMAN` count/queue, and real fenced
   APPROVE and REJECT requests. Repeat update IDs, request IDs, expired requests,
   stale fences, wrong Owner user/chat bindings and bad signatures must fail.

Rollback: use the reviewed immutable rollback map to verify the exact previous
release/manifest/artifact identities, stopped epoch, empty cgroup, direct nginx
and unit target hashes, and immutable backup paths. Do not change a release
symlink. Restore and re-verify the previous nginx configuration, reload it, then
stop and disable only `xuanjun-uk-owner-callback.service`. Do not remove callback
tables or modify task/approval rows during rollback. Retain the database backup
and evidence. The existing customer webhook and old Coordinator remain unchanged.
