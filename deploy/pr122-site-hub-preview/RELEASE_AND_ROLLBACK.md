# PR122 combined website and synthetic preview release candidate

REVIEW_ONLY / RELEASE_HOLD. This document is not a release approval.

The existing static transaction channel remains authoritative. The candidate
publisher changes only its explicit absent-baseline overlay support, with
exclusive creation, collision rejection and whole-tree final verification.
Its external approved PACKAGE_MANIFEST hash remains mandatory. The installed
publisher and original repository package are unchanged.

## Required independent approval and protected host admission

Bind exact source HEAD/tree, the review archive, both manifests, generated
publisher SHA256, the runtime sources/configuration, Hosted regression and
browser reports, and current public-tree digest. The 2026-10-16 read-only
domestic receipt proves the existing 1187 files match the approved baseline;
repeat that comparison only at activation to detect intervening changes.

Before installation, the protected operator must establish current Nginx
include placement and absence of route/zone conflicts, port 18793 availability,
the actual Python binary and supported systemd sandbox directives. No unknown
feature is a PASS. Run systemd-analyze verify and nginx -t before starting or
reloading. This candidate does not grant any new root capability to the Runner.

## Exact deployment scope

- Static release: the existing /var/www/wenwenwenyiyiyi.work release/current
  layout. Keep the frozen prior path, trusted manifest and CSP metadata.
- Preview runtime: a root-owned versioned directory beneath
  /var/lib/xuanjun-site-hub-preview; the unit above runs with a DynamicUser.
  Runtime files come only from the exact runtime entries in the approved
  package. No environment credential, production database, provider, payment,
  customer identity, outbox or messaging service is used.
- One loopback listener on 127.0.0.1:18793. One isolated, in-memory fake data
  set per anonymous session, max 64 sessions, 15-minute lifetime. Restart loses
  only synthetic data. Private project/SaaS/Finance capabilities remain closed.
- One new /_preview/community-api/ HTTPS namespace and a dedicated rate zone.
  Preserve the request Origin. Never rewrite it to 127.0.0.1 or disable checks.
  Preserve all existing sensitive-route holds, R4, OAuth, Nginx servers and TLS.

## Transaction order after approval only

1. Capture root-owned backup and exact hashes/modes/ownership of the current
   static release/CSP, affected Nginx files/includes and any preexisting preview
   unit/runtime pointer. Persist transaction intent before the first write.
2. Prepare the static release using the externally approved package hash;
   verify its 1277 public files and CSP. Do not activate yet.
3. Stage the exact preview runtime privately, verify all runtime manifest
   hashes, seal root-owned directories 0755 and files 0644, and set its version
   pointer only under the same protected transaction. Verify the unit and
   absence of unexpected sandbox warnings; start only this new unit.
4. Run loopback Host/Origin/session-isolation and fail-closed probes using only
   synthetic data. Verify the fixed listener, sandbox and no provider egress.
5. Stage the exact new Nginx includes, validate nginx -t, then use the existing
   controlled activation/reload channel. Keep both old and new objects for
   rollback; never overwrite/delete the old website release.
6. Verify real-domain TLS, all new routes, static resources, desktop/mobile,
   both ad placements, merchant/platform synthetic review, independent
   community/beneficiary views, locale and keyboard navigation. Verify two
   visitors cannot read each other's synthetic order or use each other's
   capabilities. Verify the original deep links, protected customer routes,
   winctl and existing website functions against their prior evidence.

## Failure and rollback

If any step fails or becomes unknown, hold and preserve the partial receipt;
do not blindly repeat start, activate or reload. Before activation, restore
only objects changed by this transaction. After activation, use the controlled
publisher's exact-transaction rollback to the frozen old static release and
its CSP, restore the frozen Nginx includes and any prior runtime/unit state,
validate Nginx and reload under the protected channel. Stop the newly introduced
preview unit when the prior state was absent. Prove old pointer identity,
page/resource hashes, HTTPS and health. Never remove unfamiliar runtime state
or touch DNS, P2, Finance, Binance or unrelated services.

The current artifact has no protected combined host installer or deployment
receipt. Approval, operator admission and post-release acceptance remain
required. Successful local canary or Hosted tests do not authorize production.
