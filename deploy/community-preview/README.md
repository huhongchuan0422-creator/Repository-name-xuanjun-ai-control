# Community isolated preview candidate

Status: HISTORICAL_SYNTHETIC_CANDIDATE / NOT_FOR_FORMAL_DEPLOYMENT.

Owner placement: community payment and public-benefit video run in separate containers on the existing UK host. The domestic Runner is only for existing uploads/checks. This directory's systemd/fixture server is not the formal UK backend. See docs/development/COMMUNITY_FORMAL_BACKEND_HANDOFF_20261021.md for the current routing, persistent Center binding, resource evidence and pending Owner confirmation.

## Isolation
- Proposed hostname: community-preview.wenwenwenyiyiyi.work.
- Existing apex merchant/community/mini routes are not used.
- Preview cookie is __Host-xj_community_preview; production __Host-xj_customer is rejected.
- Nginx uses the existing Unix-peer trust boundary and overwrites X-Xuanjun-Client-IP from $remote_addr.

## Experience scope
- WeChat exchange is the existing test Mock, not real wx.login/code2session.
- Center users/projects and scene shop1 are synthetic fixtures.
- business SQLite stores are temporary fixture databases.
- payments are disabled and Finance remains UNCONFIRMED.
- This demonstrates role/UI/authorization only; it is not real WeChat login, real merchant admission, real payment, settlement, or production persistence.

## Proposed URLs after approval
- Consumer mini: exact connected-preview source uses baseUrl=https://community-preview.wenwenwenyiyiyi.work and scene=shop1; current login remains synthetic Mock until AppSecret-backed admission is separately completed.
- https://community-preview.wenwenwenyiyiyi.work/
- /merchant
- /community
- /platform
- same-host APIs: /mini/login, /mini/api, /mini/logout, /community/operations, /community/directory, /community/commerce.

## Mini-program connection plan
- baseUrl=https://community-preview.wenwenwenyiyiyi.work
- commerce=true
- payments=false
- AppID stays wx1d5f8873eaea5392.
- The exact preview hostname must be in the existing mini-program request-domain allowlist before a connected preview build.
- This candidate does not modify that allowlist or account permissions.
- `prepare-mini.cjs` can create a separate connected-preview source copy with this exact baseUrl, `commerce=true`, `payments=false`; it does not upload or modify the AppID account/domain allowlist.
- Real wx.login acceptance later requires an admitted AppSecret-backed WechatCodeClient, existing account-to-openid binding, and persistent admitted Center. None is claimed here.

## Current deployment boundary

The old domestic systemd deployment candidate is superseded by the UK container placement decision. Do not execute this directory's deploy.sh to install a formal customer backend. No UK container/image/volume/network/secret binding or capacity is certified by this directory.

The original UK host manager must first provide timestamped capacity and B5/P2 reservation evidence, existing container/runtime identifiers and actual ingress mapping. The original Center owner must supply its actual instance/data location and approved same-process integration or migration/service-boundary plan. Then prepare an exact UK container release, limits and rollback candidate for Owner confirmation. Numeric CPU/memory/PID/disk/log limits remain HOLD until supported by evidence; no new credentials, accounts or permissions are created here.

Historical rollback tests for deploy.sh remain development evidence only. They are not authority to deploy on either host. The BACKEND_NOT_READY upload gate remains mandatory.
