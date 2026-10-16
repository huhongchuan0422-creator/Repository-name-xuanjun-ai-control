# PR122 static experience update over deployed r2

Review-only. No release permission is bundled. No production action has been executed by this change.

## Exact scope

Content commit: `2ecee38d65b0c5353521019dd08030245e902e0d`.
The containing commit adds only packaging, transaction controls, evidence and CI.

The existing three navigation names and links remain. Home exposes four business
sections with direct product, visual, co-creation/ecology and customer entrances.
Ecology links belong to the existing Labs/co-creation entry. The mobile header
aligns its logo/menu/language controls. Only the dropdown glyph rotates. The new
Chinese merchant dashboard offers three clearly marked fictional merchants.

Old r2 public tree: 1,277 files. New tree: 1,279 files; 357 existing files change,
two files are added, none are removed. The runtime, its unit, limits, preview
proxy rules and publisher bytes are unchanged. The existing 356 ICP footers are retained; the new merchant page adds its own ICP footer. The 31 unchanged developer-demo/legal overlay pages that did not have this footer remain outside that inherited 356-page scope.

## Protected transaction

ID: `pr122-hub-experience-20261016`.
New release: `pr122-hub-experience-2ecee38d`.
Previous release: `pr122-site-hub-dd810410`.
Domestic host only: `iZvt5t8tlrm8oiZ`.

`HOST_PINS.json` binds the Owner's read-only evidence: exact r2 receipt, all 1,277
old public files through the approved candidate manifest, and the 13 actual Nginx
source files/hashes. Its pins are checked again during execution. A changed r2
receipt or changed website/configuration causes HOLD, rather than inheriting an
unknown state.

The update reuses the reviewed publisher's prepare/activate/check/rollback and
its pointer envelopes. The old full combined apply is not called. The new
controller shares the old controller lock. It creates a unique transaction,
verifies a complete backup, seals the package, prepares the new immutable release,
CAS-replaces only `/etc/nginx/pr122-site-hub/locations.conf`, runs `nginx -t`,
rechecks approval/drift/runtime isolation, activates the new pointer, reloads
Nginx, verifies HTTPS file bytes/security headers and checks all public hashes.
CSP follows the existing current-release metadata include.

There are 182 exact static routes: 137 file routes and 45 redirects. The unchanged
preview proxy is appended. Existing broad routes and server blocks are retained.
HTTPS checks additionally cover every changed overlay file, including all three
homepages and shared CSS. The previous preview smoke creates synthetic test
sessions/orders only; no payment provider is connected.

The controller never installs, starts, stops or replaces the already deployed
Runtime, changes DNS, modifies Tokyo, or overwrites the installed publisher.
Its existing systemd unit, source files, active identity and effective BPF/mount
sandbox are verified before activation and when rolling back.

## New independent gate

A new independent incremental review must cover the exact containing commit/tree,
Hosted run/artifact, new static and distribution package bytes, this controller,
pins, actual delta, test evidence and this plan. Old page/backend audits are
inherited only where bytes are unchanged. No author self-signing.

The new approval must provide these machine fields (not an executable template):

- decision `RELEASE_APPROVED`; operation `PR122_STATIC_EXPERIENCE`;
- fixed transaction ID and content commit above;
- exact wrapper, HOST_PINS, static TAR and PACKAGE_MANIFEST SHA256;
- previous_receipt_sha256 from HOST_PINS;
- independent_review `PASS`, reviewer_role `INDEPENDENT_AUDITOR`;
- real review_comment_id and release_comment_id newer than 6209244057;
- issued_unix/expires_unix, valid at most two hours;
- rollback_approved true and max_executions 1.

The Owner bootstrap must fetch the real approval comment from PR122, verify its
exact machine fields/ID, and save it root-private mode 0600. A local JSON fabricated
by the code author is not approval. It must verify the downloaded distribution
TAR, its manifest and every member before executing anything. Reuse the original
source archive already on the target only after SHA256 validation; it is excluded
from the small distribution intentionally. Do not invoke apply before this gate.

## Failure and rollback

No automatic apply retry or resume. Preserve receipt, logs, backup, old release
and all r1/r2 evidence. On failure inspect the durable phase/intent. The explicit
rollback command uses the same inputs and only this transaction's identity.

Rollback first verifies all backup hashes, expected old/new pointer identities,
Nginx source inventory and unchanged Runtime. It delegates pointer recovery to
the reviewed publisher, restores only its own exact locations replacement,
validates/reloads Nginx, and verifies all old public/config hashes. Foreign config,
unknown current or unverifiable backup causes HOLD without guessing ownership.
The new release and evidence remain for inspection. The Runtime stays active.

After apply or rollback, a real desktop/mobile HTTPS browser must verify the
visible result. Fixture/loopback tests and curl are not production visual approval.
The controller returns HTTPS_SMOKE_PASS_AWAIT_BROWSER, never a final browser PASS.

## Remaining business limits

New merchant dashboard is Chinese and uses independent fictional fixture data;
it is not synchronized with the old consumer/runtime orders. Existing developer
role tools remain accessible. English entry explains the Chinese dashboard. Real
identity/balance/checkout/payment/refunds/commission settlement are not enabled.
Customer access stays governed by existing routes/permissions. Broader multi-role
product UI work is not falsely described as complete by this static update.
