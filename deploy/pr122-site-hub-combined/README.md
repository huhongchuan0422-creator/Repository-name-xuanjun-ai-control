# PR122 combined host wrapper — REVIEW ONLY / production HOLD

This new wrapper reuses the independently reviewed 447-member artifact and its
generated publisher byte-for-byte. It does not rebuild pages, replace the
installed publisher, grant Runner sudo, or replace the old website. The manual
admin root channel is the candidate execution channel; it still needs explicit
admission for this exact wrapper. The old Portal logfix capability is unrelated.

## Evidence and new scope

Audited application: dd81041042ef3acca031d6b64684941c38ed72ef,
Tree 01a6cef8e54ffae7357fbcbcc9417314b7bce4aa. Audit #6207779869 grants
AUDIT_PASS_WITH_SCOPE_LIMITS, not production release. Host non-root inspection:
Run 38848902571 / Job 116805523238 / #6207852348. Owner's root terminal evidence:
#6207883697 at 2026-10-16 04:09:50 UTC. Root nginx -t passed; current and installed
publisher remained at the old baseline. /var/backups was absent.

New review scope: combined.py, its package builder, HOST_PINS, exact route
generation, the root-private gate and journal, backup/restore and recovery,
host adaptation, new tests and workflow. Reuse unchanged page, browser, preview,
publisher delta, original publisher regression and frozen artifact evidence.

The existing apex catch-all returns 404. A new include adds exact locations for
the 90 manifest-bound new files, index aliases and canonical 308 redirects.
It also includes the approved /_preview/community-api/ proxy unchanged. Broad
customer or filesystem prefixes are never exposed. Existing locale/assets
routes, upstreams, winctl servers, certificates and DNS are retained. The HTTPS
file is modified at exactly one existing include anchor only after its live
SHA256 matches HOST_PINS. All 11 expanded configuration sources must match;
new or changed includes stop execution. The pre-activation drift check also
requires the expected new 2 config sources and no other changes.

## Inputs and admission

Root-owned immutable input directory, with non-writable ancestry:

- PR122_SITE_HUB_REVIEW_ONLY.tar.gz — frozen SHA256 18cd49ff3936895171b889099871e58dd2f1576508c8dc3e4db16a9fd935902e.
- PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz — SHA256 74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63.

No root approval is included. A protected operator must first verify the external
distribution manifest/hash and independently approved wrapper hash, then admit
a root-owned approval JSON containing all of these fields:

- decision RELEASE_APPROVED; operation PR122_COMBINED_WEBSITE.
- exact transaction_id, source_head, wrapper_sha256, host_pins_sha256,
  static_artifact_sha256, package_manifest_sha256.
- independent_review PASS, reviewer_role INDEPENDENT_AUDITOR, a new
  review_comment_id approving this exact wrapper and a release_comment_id
  recording a separate production decision (both after #6207883697).
- issued_unix and expires_unix: integers, valid now, lifetime at most 24 hours.

The JSON is an operator-admitted gate record, not a cryptographic assertion of
GitHub authorship. Comment IDs alone do not authenticate an independent review.
The operator must read the actual comments and verify their exact bindings and
reviewer independence before creating this record. Code author cannot self-sign
PASS. The wrapper cannot manufacture or fetch an approval. Root status alone
does not grant release. No generic command, environment-controlled host, webroot
override, non-root CLI mode or arbitrary helper installation is supported.

## Transaction and backups

All control data lives at /var/lib/xuanjun-pr122-site-hub, mode 0700; transaction
IDs name fixed child directories. An exclusive controller lock prevents overlap
and the existing publisher lock protects its own phases. Apply creates durable
intent/completion markers around every stage; the same ID cannot be reapplied.

1. Verify both archives, all 446 members, publisher hash, host config, 1187 live
   file digest, vacant port and absent new unit/runtime/config objects.
2. Before production writes, save all 11 config sources plus the previous 1187
   public files and both inline-CSP conf/JSON in a root-private backup. Read the archive
   back and compare every member's bytes. Preserve the old release in place.
3. Seal the frozen bundle privately; invoke the existing reviewed publisher
   prepare. Stage approved runtime files, unit and one exact enable symlink;
   verify the unit, reload only systemd's manager, start only the new service.
4. Verify non-root runtime UID, no capabilities, NoNewPrivs, separate mount
   namespace, exact unit restrictions, memory/tasks/address-family settings,
   loopback listener PID and effective ingress/egress cgroup BPF filters.
   Unsupported or unreadable BPF is HOLD, never a weakened fallback.
5. Exercise two synthetic sessions, order and admin isolation, CSRF/404 cases.
   Install only the exact new Nginx includes and anchor patch; nginx -t; compare
   config and old public files again, then activate with the reviewed publisher.
6. Reload Nginx; check real HTTPS exact new file bytes, CSP headers and negative
   paths; repeat synthetic isolation through HTTPS; run publisher check.
   End state is HTTPS_SMOKE_PASS_AWAIT_BROWSER, never full acceptance.

Each fixed subprocess has a 25-second deadline, HTTP requests 5/8 seconds, service
readiness 8 seconds, publisher phases 120 seconds; steps check an overall
600-second budget. This is not a kernel-enforced whole-process deadline.
SIGTERM/ordinary failures record HOLD_PARTIAL. SIGKILL/power loss leave the last
durable intent; do not reapply. Inspect status and explicitly roll back this ID.

Rollback does not require an unexpired release gate. It requires the same wrapper
and pins, sealed receipt, input hashes, complete verified backup, known current
pointer and matching changed objects. Unknown or partially written objects are
held for manual reconciliation, never blindly deleted. The existing publisher
reconciles interrupted pointer changes and performs static rollback. Restore
the pinned Nginx file, remove only exact new config/unit/enable/runtime-pointer
objects, stop only the owned preview service, nginx -t and reload; verify old
pointer, all old public bytes and original config hashes. Immutable candidate
release/runtime directories and all transaction evidence remain for inspection.
Backup extraction is not used to overwrite an unknown old release. If the old
release has changed or disappeared, HOLD for protected recovery; this wrapper
does not invent a destructive restore path.

## Test and acceptance boundaries

Local integration uses actual original archive + frozen review artifact, full
1277-file candidate, real filesystem and real reviewed publisher. systemd,
kernel sandbox and Nginx effects are explicit test doubles. Hosted fallback
uses a labelled synthetic 1187+90 file fixture because the original full source
archive is not in this public repository. It must not be reported as original
production source acceptance. The frozen real 447-member archive is separately
verified in both environments. Hosted Nginx routing test uses a temporary
configuration and actual approved loopback runtime; it is not domestic-host
systemd/BPF/HTTPS acceptance. Actual target sandbox support remains unknown
until an approved installation reaches that check.

After approved deployment, desktop/mobile real HTTPS browser acceptance must
cover original three menu contents and 5px arrows, locales, keyboard, all new
pages/assets, six demo roles, two ads, refresh, customer capability holds,
original deep links and prior unrelated function evidence. Failure or uncertain
state triggers HOLD and transaction-specific rollback. Browser acceptance and
post-rollback HTTPS validation remain separate evidence, not inferred from a
publisher PASS. This package does not execute these production steps in CI.

Do not execute until the separate wrapper review and release decision exist.
No DNS, P2, Finance, Binance, secrets, real payments or unrelated services are
in scope. Hosted success is never a production deployment receipt.
