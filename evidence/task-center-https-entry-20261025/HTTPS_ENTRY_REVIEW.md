# 任务中心受保护 HTTPS 入口候选（未部署）

## 实测入口与冲突

- 当前真实域名：`uk.wenwenwenyiyiyi.work`，DNS A=`8.208.119.115`。
- 当前证书：CN/SAN 均仅 `uk.wenwenwenyiyiyi.work`；Let's Encrypt YR1；有效期
  `2026-10-14 10:49:42Z` 至 `2027-01-12 10:49:41Z`；SHA256 指纹
  `F7:CA:AA:ED:2C:24:58:2A:22:DF:2F:47:08:E8:14:0A:8F:27:00:7D:64:F1:DD:94:36:CE:97:2E:14:5F:C6:F6`。
- 没有证据表明已有另一子域或证书 SAN 可直接复用，因此不猜测独立子域。
- 候选 URL：`https://uk.wenwenwenyiyiyi.work/task-center-test/`。
- 当前该路径返回 404；`/owner/` 与 `/owner/api/state` 属于旧 `127.0.0.1:18556`
  上游且实测 502，禁止恢复或复用。
- `/etc/nginx/community-preview.inc` 为 root:root 0600，当前只读身份不能读取。
  因此隐藏 location 冲突为 `UNKNOWN`；实际变更前须由既有管理员执行一次完整只读
  `nginx -T` 并确认没有 `/task-center-test` 重叠项。

## 源码候选

基线：`bc31709d9e013936125a1c246e2a48ae6715a605`。本分支只增加：

- 固定 `--external-origin https://uk.wenwenwenyiyiyi.work`；只接受 HTTPS 且不含路径、
  用户信息、query 或 fragment。
- 固定 `--base-path /task-center-test/`，服务端直接解析并拒绝前缀外请求。
- 外部模式直接核 HTTP `Host` 与浏览器 `Origin`；不读取、不信任
  `X-Forwarded-Host`、`X-Forwarded-Proto` 或客户端伪造转发头。
- 页面 API、资源、跳转全部使用 base-path 相对地址。
- 会话和 CSRF Cookie 的 Path 固定 `/task-center-test/`；HTTPS 模式增加 Secure；
  会话 Cookie 保持 HttpOnly，二者保持 SameSite=Strict；退出用相同属性清除。
- 默认 loopback 模式保持兼容，不改变现有 release。

新 release 的 unit 参数应在既有参数末尾增加（尚未执行）：

```text
--external-origin https://uk.wenwenwenyiyiyi.work --base-path /task-center-test/
```

## Nginx 精确增量

将同目录 `nginx-task-center-test.location.conf` 的两个 location 加入现有
`server_name uk.wenwenwenyiyiyi.work` server block。`proxy_pass` **不得带尾斜杠**，以便
上游收到并校验完整 `/task-center-test/` 前缀。后端不依赖转发头；Host 固定为已审域名。
不改证书、DNS、防火墙、443 listen、旧 `/owner` 或 community/B5 include。

## 待 Owner 审批后的执行顺序

1. 管理员只读完整 `nginx -T`，确认 root-only include 不含同路径冲突。
2. 校验新冻结包 Manifest/SHA，在新的不可覆盖 release 目录解包；不触碰 bc317 release、
   v3 DB、五个 TEST_ONLY 身份文件或任何密钥。
3. 备份 unit 与 Nginx server 文件；先在副本生成精确 diff。
4. unit 仅增加上述两个参数；Nginx 仅增加两个 location。执行 `nginx -t` 成功后才原子安装。
5. 原子切换 `current` 到新 release，`daemon-reload`，重启 task-center unit，再 reload Nginx。
6. 依次验证 loopback health/ready、HTTPS 登录/退出、角色流程、错 Host/Origin/CSRF 拒绝，
   模型出站仍 DISABLED。浏览器验收前不得写成 ACCEPTED。

外部模式下 loopback 请求也必须带已审 Host 与完整 base path，例如：

```bash
curl --fail --silent -H 'Host: uk.wenwenwenyiyiyi.work' \
  http://127.0.0.1:8765/task-center-test/healthz
curl --fail --silent -H 'Host: uk.wenwenwenyiyiyi.work' \
  http://127.0.0.1:8765/task-center-test/readyz
```

## 回滚（任何一步失败）

1. 停止任务中心并确认进程停止、8765 释放；停止失败时保留 current，不继续切换。
2. 恢复原 unit 与 `current` 到 bc317 精确 release，启动后核 loopback health/ready。
3. 恢复 Nginx 原文件，`nginx -t` 通过后 reload；候选 location 消失应恢复 404。
4. 保留新 release、日志和 v3 DB 现场；不重建 DB、不重新生成账号或密钥。

## 当前状态

- bc317 已部署：由 Owner 提供，且本机只读观测 unit active、loopback 8765、health
  `TEST_ONLY/DISABLED/UP`。
- 新源码：本地隔离实现并测试；尚未部署。
- Nginx/DNS/TLS/防火墙：本轮未修改。
- 真实 HTTPS 浏览器验收：`NOT_EXECUTED`。
