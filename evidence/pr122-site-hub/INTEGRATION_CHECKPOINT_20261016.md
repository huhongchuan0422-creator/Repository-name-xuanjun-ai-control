# PR122 website integration checkpoint — 2026-10-16

Status: ISOLATED_INTEGRATION_CANDIDATE / PRODUCTION_HOLD.

Authority remains PR122. No parallel issue or PR is created. Original handoff
HEAD aed5820c4dd8ca6f7e9a2020ea92a498cb41ae76, tree
1baf3eff8072fa53ea6cebc6459a4cab7c1db119. Original handoff files are unchanged.

## Actual work completed

- Retrieved all 19 handoff files and inspected 15 HTML pages.
- Retrieved the original 1187-file source archive and verified SHA256
  74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63.
- Browser-observed live HTTPS homepage and successfully switched to the
  English homepage. Confirmed `.primary-nav`, `.nav-group > a`,
  `.nav-group > button`, `.nav-panel` match the source baseline.
- Built an isolated 1203-file candidate using the pinned archive. Fourteen
  new content pages reuse the original Chinese header/footer, original
  yunhui.js and scoped integration CSS. The handoff index is never copied.
- Added the requested submenu entries, a Custom & Delivery submenu retaining
  its existing destination, and an additional homepage discovery section.
  Existing homepage hero and SEO metadata remain intact.
- Checked 314 original navigable HTML pages: all original link targets,
  title and main content retained, with only an appended discovery section
  allowed on the three existing homepages. Remaining original files retained.
- Quote regression passed locally: 6000 → 2400 → 1200; ordinary 90% cap,
  custom 50% cap and COST_UNKNOWN behavior included. Community frontend
  synthetic tests: 40/40 passed. Neither is production/browser acceptance.

## Consolidated remaining requirements

1. Reconcile this pinned archive with the live current release and retain its
   approved TikTok correction. This stage builder intentionally cannot activate
   or replace production. It is not a replacement for the controlled publisher.
2. Supply English content for the fourteen new pages. Existing English pages
   remain English; new menu links explicitly identify Chinese previews.
3. Community demo is not a static-only app. `/demo/orders`, simulation,
   storefront, role panels and other `/demo/*` calls require the existing
   isolated simulation service. No API is enabled, copied or reimplemented.
   Existing absolute `/demo/*.js`, merchant/platform aliases and relative
   legal/visual links must be mapped and checked together with the service.
4. Generate exact CSP hashes for final HTML or externalize the calculator's
   inline script. Never use unsafe-inline to satisfy the test.
5. Complete desktop/mobile browser tests, accessible keyboard navigation,
   403/404, actual demo flows, resources and deep-link regression. The CSS
   candidate uses a 5px desktop column gap and verified selectors; measured
   text-to-arrow geometry and mobile acceptance are still PENDING.
6. Independent reviewer must assess the complete final integration diff,
   exact source/tree, manifest, CI, browser report and controlled release /
   backup / rollback package. This author has not signed an independent PASS.
7. Publish only through the existing Release Gate, then verify real URLs and
   restore evidence. No server deployment, current pointer, DNS, P2, Finance,
   Binance, credentials or real-payment capability changed in this work.

The workflow added here provides exact-commit inventory and synthetic
regressions only. It deliberately does not claim staging/browser/production
acceptance or manufacture an independent approval. The private original
archive is not embedded in public CI artifacts.
