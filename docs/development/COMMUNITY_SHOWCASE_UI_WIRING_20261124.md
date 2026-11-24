# Original catalog page showcase wiring (delta afterc467e70b)

## Existing-entry finding
Live workbench.js536126eb has only configureCommunityWorkbench/applyCommunityWorkbenchHash/syncCommunityWorkbenchView as presentation hooks. Its call closure (around50) always uses auth.workspace; itemForm117 submits ordinary {item}, then commerce.price_set. settings108 expects r.items/profile. Neither understands Showcase flat item params, raw gallery, published or its {record} read contract. Reconfiguring that ordinary form to owner_merchant or passing Showcase params there is NOT a valid platform listing path.

Live web-session.jse402fe20 owns the legitimate cookie/CSRF session closure, but its adminCall/call are private and exposed change-password/home-metrics methods are not generic operation APIs. Existing configureCommunityWorkbench is NOT an authorized general-purpose sender. No existing public app function for Showcase was found; no token/cookie/sessionStorage/CSRF inspection is proposed. This is an internal UI omission, not Owner login/permission/TTY lack.

## Minimal two-file business delta, original25c writer
- scripts/community_web_session.py: original /community/session/check optionally returns platform_showcase={workspace,display_only:true}, only from the actually mounted protected Showcase matching original ROOT UID/project/tenant/Center and persistent scope/capabilities. No grant, policy, user or session mutation. Old/nonroot/no-mount replies remain unchanged.
- demos/community-stage/web-session.js: original session check carries that nonsecret reference into a dedicated Platform display section prepended INSIDE existing #catalog-management. Existing owner_merchant forms, workbench.js/HTML/f7d/ads remain untouched. The original closure sends the original same-origin /community-preview/community/operations request with its own existing CSRF; no secrets are returned/exposed. No new backend/route/port or role.

The platform panel has four JPEG previews, multi-line original description, editable price/quantity and explicit display-only publish. JSON import does not write. The Save and list action intentionally publishes=true even when the original content draft was unpublished; this follows the existing Owner listing instruction, not an automatic write on login/import. It first reads community.merchant_settings, uses the actual version, writes flat community.item only if fields differ, then reads actual record back. Unknown write effects are not auto-replayed. Ordinary merchant {item}/price_set is never used for this panel.

## Public app wrapper for main's EXISTING browser context (candidate until installed)
In the already logged-in merchant iframe, window.communityPlatformShowcase exposes ONLY:
- read(): original API read, returns product data/record only.
- loadDraft(approvedContent): populates the same visible four-image form; no request/write.
- publishDraft(approvedContent optional): same explicit UI publish action, version-read→save→readback; no credentials/workspace/operation override arguments.

The outer portal does not host this editor. Use the existing same-origin iframe /community-preview/merchant/workbench?embedded=1...#catalog-management, NOT a new profile/page/backend. After reviewed installation, normal refresh retains the Owner session; original session/check discovers Showcase automatically. No repeated Owner login/TTY or store selection is required for platform operations.

Example after installation in the iframe context: await window.communityPlatformShowcase.read(). In outer same-origin portal main may use iframe.contentWindow.communityPlatformShowcase, NOT read any credential storage or DOM credential fields. For readback return only record id/quantity/unit_minor/published/version/gallery.length; do not dump large images unnecessarily.

Prepared public content file lives in the task delivery POMELO-WHITE-M2.platform-publish.json: idPOMELO-WHITE-M2, quantity100, unit_minor1000, publishedtrue, four exact approved photo hashes unchanged, no guessed expected_version. SHA0fa9b490ce014638d1dd172c0ff4fdf01fcabd4242c49307e3ba9daf54397cbd. It is only input data, not a publication receipt. Main can upload it through the new normal form file input or pass its parsed product content to publishDraft; never pass a token/CSRF/session value. No instruction asks Owner to manually operate the catalog.

## Tests/evidence
- New UI factory: eight directed synthetic DOM cases against exact source and merged-runtime JS: no-reference denies/no IO, read/save/read targetplatform_showcase only,100/1000/four images, existing version7, duplicate content avoids new write, original unpublished draft publishes explicitly, unknown write no retry, malformed gallery/wrong existing ID, session change/single-flight. Original session-race regression also passes for source and runtime.
- Python: four new nonsecret reference/ROOT/delegate/revocation/foreign realm/no-write cases plus five directly affected original WebSession cases pass9/9. Source Python result is byte-identical to runtime candidate.
- Synthetic VM/service checks are NOT a real browser visual or live product listing acceptance. Real Owner cookie context never inspected/exported. Old quantity/backend/permission tests are unchanged and reused.

## Runtime/source identity and install boundary
Git JS baseline differs from newer deployed JS (owner account presentation). Do NOT install old Git source whole-file over live. deploy/community-preview/showcase-ui-session-runtime.delta.patch is the exact additive patch on live e402fe207f0fcaeee8b2b682c01b61d813f49d64608c00cc6dae74e0449ce2c9; runtime identities bind the exact result. This zero-context delta is applied with git apply --unidiff-zero in an isolated copy; production install uses the exact pinned merged artifact. Python base2d7793274b621cb6eae8d35bcba595606233f774979ea7091fb0732e44d4af96.

Only after nonauthor review and main's serial maintenance window, original writer applies the two-file overlay through existing namespace/nine-lock/native coordinator, preserving current Host1e6f/ROOTrev4/165/sessions/nginx/f7d. Source/config/DB/authority have NOT been installed/changed by this candidate step; no merchant or Showcase product write occurred. Existing session is preserved by source restart, not reset. Two old file backups suffice for code rollback; no authority/data rollback is introduced. After install main uses its original browser for normal platform form/API wrapper publish and real record/public recommendation/detail proof. Goal100 remainsOPEN until that.
