# Unified Admin Model Platform Candidate — affected-scope results

- Baseline Commit: `c8a983daea6eaaf33e619e8f08a54605535ca028`
- Baseline Tree: `0b0cfab4df6e41fdf8519446635b4625fb87268a`
- State: UI / projection candidate; **NOT_DEPLOYED / NOT_ACCEPTED**
- Live platform registry/config read: **UNKNOWN** (root-protected current SQLite parent; no credential or permission expansion attempted)

## Tests

- `python3 -m unittest tests.test_unified_admin_projection`: **7/7 PASS**
- `python3 -m unittest tests.test_task_center_app.TaskCenterAppTests.test_workbench_host_and_admin_projection_are_read_only`: **1/1 PASS**
- `node demos/owner-workbench-v2/tests/workbench.test.cjs`: **45/45 PASS**
- `git diff --check`: **PASS**

## Render inspection

- Desktop PNG: `model-platform-desktop.png`
  - SHA-256: `4b62683f56c9a9728e92eb2347a2b234e0b9ec715eda380d7e8ed892e5c1b248`
- Mobile PNG: `model-platform-mobile.png`
  - SHA-256: `3820dc9f5a404a77da7e5acb83a60e1754965ee5b3c7e59ae24cad4f5cfc0b06`
- Visual result: platform cards, three short steps, paid-test confirmation, protected-reference advanced details, and single-admin navigation render readably at 1440 px and 390 px widths.
- OpenClaw browser handler was unavailable; screenshots were rendered with the already-installed local Chromium/Playwright runtime. No external request, provider call, credential, or deployment occurred.

## Scope boundary

- Reuses existing fixed platform presets and ModelControl actions.
- Does not modify official website, SaaS purchase UI, community mini-program/admin, or OCR.
- Does not introduce a customer-management page, arbitrary provider URL, persistent browser credential storage, new sudo, or new permission.
