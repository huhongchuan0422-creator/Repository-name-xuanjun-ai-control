# PR122 Domestic Website Delta Candidate

Status: `OFFLINE_CANDIDATE / PRODUCTION_HOLD`.

This directory is a delta package. It does **not** contain or rebuild the
immutable 1187-file Tokyo source archive. `source-pin.json` binds that archive;
`overlay/` contains the one approved source correction; and
`candidate-manifest.json` describes the complete expected release after the
overlay is applied.

## Exact namespaces

- Private control base: `/home/openclaw_ops/v8-domestic-operations/website`
  remains behind `/home/openclaw_ops` mode `0700`.
- Root-managed public base: `/var/www/wenwenwenyiyiyi.work`.
- Public releases: `/var/www/wenwenwenyiyiyi.work/releases/<release_id>/public`.
- Public pointer: `/var/www/wenwenwenyiyiyi.work/current`.
- Root transaction receipts: `/var/www/wenwenwenyiyiyi.work/transactions` mode
  `0700`.

The Nginx worker reads only the root-managed public tree. No candidate requires
traversal of `/home/openclaw_ops` and no candidate edits the existing `winctl`
server blocks or certificates.

## Candidate sequence (not executed)

1. Independently verify the delta bundle and pinned source archive hashes.
2. Run `bin/pr122_website_release.py prepare` only under a later Gate. Private
   staging remains 0700; the final release is root-owned directories 0755 and
   files 0644. The receipt embeds the trusted Manifest and binds the source,
   source pin and package hashes. It also generates the exact inline CSP hash
   include under `current/release-metadata`.
3. Install the exact apex HTTP bootstrap only after config conflict review;
   run `nginx -t`; do not reload without the Gate.
4. Apex DNS remains on Tokyo. The separate Tokyo candidate forwards only the
   ACME challenge prefix to Domestic. Domestic reuses proven
   `/usr/local/bin/certbot` 5.8.0; no PATH assumption or DNS cutover is used.
   After both-host routing is proven, run `issue-apex-certificate.sh` with its exact
   approval argument. Install the apex HTTPS and isolated renewal candidates;
   verify `nginx -t`, SAN/chain, renewal dry-run and existing winctl health.
5. Run `activate`, then `check`. A durable activation intent precedes pointer
   replacement; after interruption use only `reconcile`, never blind retry.
   DNS remains unchanged until independent
   review and a separate Owner-approved cutover.
6. Use `rollback` only for the exact transaction. Pointer identity drift or an
   unknown result stops without blind retry.

Every failure, timeout, partial state or unknown state is `HOLD`. A prepared
release is not an active release; an active release is not a production
deployment; and an Nginx syntax pass is not DNS/TLS/business acceptance.
`cutover-gate.json` remains HOLD while any dynamic route is unresolved.
`production-action-contract.json` defines the cross-object backup/rollback
order, and `PRODUCTION_EXECUTION.lock` intentionally prevents treating this
offline package as an executable installer.

## Explicitly incomplete

The `/visual/community-payment/` preview, controlled tenant/project API,
merchant review/correction/re-review, durable trusted feedback, and live
TikTok/Douyin/Telegram/WeCom/Novel backends remain owned by their original
developers and Release Gates. The dynamic-hold include returns fail-closed
responses until those dependencies have accepted commits and evidence. No
payment, finance, customer message or production write is enabled here.
