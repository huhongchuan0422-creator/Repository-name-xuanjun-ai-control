# 英国 443 只读盘点（2026-10-25 22:49 CST）

- 主机：`iZd7oeikknn1z21sq6ji6zZ`。
- 443：Nginx 监听 `0.0.0.0:443`。
- server：`uk.wenwenwenyiyiyi.work`，TLS 1.2/1.3，HSTS；公网解析 `8.208.119.115`。
- 证书公开元数据：CN/SAN=`uk.wenwenwenyiyiyi.work`；issuer=`Let's Encrypt YR1`；
  serial=`05DB5A1D47228854CC5A10B686CBFB960B9A`；有效期
  `2026-10-14T10:49:42Z..2027-01-12T10:49:41Z`；SHA256 fingerprint
  `F7:CA:AA:ED:2C:24:58:2A:22:DF:2F:47:08:E8:14:0A:8F:27:00:7D:64:F1:DD:94:36:CE:97:2E:14:5F:C6:F6`。
- 可读 Nginx 配置：`/owner-callback` → `127.0.0.1:18557`；`/owner/` 和
  `/owner/api/state` → `127.0.0.1:18556`；其余 root location 返回 404。
- 公网实测：`/`、`/login.html`、`/healthz` 返回 404；`/owner/` 与
  `/owner/api/state` 返回 502。
- root-only include：`/etc/nginx/community-preview.inc`，root:root 0600；当前身份读取被拒。
- 已部署任务中心：systemd unit active；进程以独立服务身份运行；只监听
  `127.0.0.1:8765`；loopback `/healthz` 返回
  `{"mode":"TEST_ONLY","outbound":"DISABLED","state":"UP"}`。
- 本轮没有读取证书私钥、服务密钥、账号文件或数据库内容；没有执行提权、Nginx reload、
  unit restart、DNS/TLS/防火墙修改。
