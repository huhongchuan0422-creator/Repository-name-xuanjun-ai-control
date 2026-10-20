# Community isolated preview candidate

Status: CANDIDATE_ONLY / NOT_DEPLOYED.

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
- Real wx.login acceptance later requires an admitted AppSecret-backed WechatCodeClient, existing account-to-openid binding, and persistent admitted Center. None is claimed here.

## Required later authorization
1. DNS for the dedicated hostname.
2. TLS certificate covering that hostname.
3. Root execution on the domestic host.
4. Create only /opt/xuanjun-community-preview/**, /etc/systemd/system/xuanjun-community-preview.service, /etc/nginx/conf.d/xuanjun-community-preview.conf, and /run/xuanjun-community-preview/preview.sock.
5. Reload Nginx and start/stop only this preview unit.
6. If mini access is desired, add only this hostname to the existing mini-program request-domain allowlist.

The deploy candidate saves old current/unit/nginx/enabled/active state before mutation. Installation, nginx validation, service start, internal HTTPS, DNS-path, and public HTTPS failures are all inside rollback coverage.
The GitHub workflow is package-only and cannot deploy.
