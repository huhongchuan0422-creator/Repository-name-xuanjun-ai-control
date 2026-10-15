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
2. Run `bin/pr122_website_release.py prepare` as root under the approved Release
   Gate. It validates archive identity/member types, overlay baseline, and the
   complete post-overlay manifest before installing an immutable release.
3. Install the exact apex HTTP bootstrap only after config conflict review;
   run `nginx -t`; do not reload without the Gate.
4. After ACME routing is proven, run `issue-apex-certificate.sh` with its exact
   approval argument. Install the apex HTTPS and isolated renewal candidates;
   verify `nginx -t`, SAN/chain, renewal dry-run and existing winctl health.
5. Run `activate`, then `check`. DNS remains unchanged until independent
   review and a separate Owner-approved cutover.
6. Use `rollback` only for the exact transaction. Pointer identity drift or an
   unknown result stops without blind retry.

Every failure, timeout, partial state or unknown state is `HOLD`. A prepared
release is not an active release; an active release is not a production
deployment; and an Nginx syntax pass is not DNS/TLS/business acceptance.

## Explicitly incomplete

The `/visual/community-payment/` preview, controlled tenant/project API,
merchant review/correction/re-review, durable trusted feedback, and live
TikTok/Douyin/Telegram/WeCom/Novel backends remain owned by their original
developers and Release Gates. The dynamic-hold include returns fail-closed
responses until those dependencies have accepted commits and evidence. No
payment, finance, customer message or production write is enabled here.
