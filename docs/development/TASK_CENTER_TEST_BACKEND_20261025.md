# 任务中心后台测试版（TEST_ONLY）

## 已实现与边界

本测试版沿用同一 Supervisor/Gateway/SQLite；没有第二任务库。页面、管理 API、
会话和 TEST_ONLY 队列都绑定同一数据库。监听固定为 loopback；默认禁止 Provider、
Codex 真实出站。`FileTestIdentityProvider` 只是隔离验收适配器，生产接入必须替换为
原统一身份提供方；当前仓库没有该生产适配器，不能把本地账号称作正式账号。

## 一次性准备（尚未替 Owner 执行）

以下目录、数据库和凭据均为新建隔离测试资产，不得指向业务库。凭据命令交互读取
密码，不在参数、终端历史或本文中保存明文：

```bash
install -d -m 700 /ABSOLUTE/TEST/DIR
python3 scripts/reusable_scheduler_cli.py \
  --db /ABSOLUTE/TEST/DIR/task-center.sqlite3 \
  --test-authority-key REPLACE_WITH_TEST_AUTHORITY_KEY \
  app-demo --tenant tenant-test --lock-root /ABSOLUTE/TEST/DIR/locks
python3 - <<'PY'
from cryptography.fernet import Fernet
p='/ABSOLUTE/TEST/DIR/model.key'
open(p,'wb').write(Fernet.generate_key()+b'\n')
PY
chmod 600 /ABSOLUTE/TEST/DIR/model.key
python3 scripts/task_center_test_identity_cli.py \
  --output /ABSOLUTE/TEST/DIR/identities.json \
  --tenant tenant-test --username OWNER_CHOSEN_TEST_USER \
  --principal OWNER_CHOSEN_TEST_PRINCIPAL \
  --roles TASK_CENTER_ADMIN,TASK_EXECUTOR
```

跨角色验收需要分别创建登录主体；每次执行命令时使用不同用户名、主体和交互输入的
不同测试密码，不能共享管理员身份：

```bash
python3 scripts/task_center_test_identity_cli.py --append --output /ABSOLUTE/TEST/DIR/identities.json --tenant tenant-test --username TEST_EXECUTOR --principal TEST_EXECUTOR_PRINCIPAL --roles TASK_EXECUTOR
python3 scripts/task_center_test_identity_cli.py --append --output /ABSOLUTE/TEST/DIR/identities.json --tenant tenant-test --username TEST_QA --principal TEST_QA_PRINCIPAL --roles TASK_REVIEWER
python3 scripts/task_center_test_identity_cli.py --append --output /ABSOLUTE/TEST/DIR/identities.json --tenant tenant-test --username TEST_SECURITY --principal TEST_SECURITY_PRINCIPAL --roles TASK_REVIEWER
python3 scripts/task_center_test_identity_cli.py --append --output /ABSOLUTE/TEST/DIR/identities.json --tenant tenant-test --username TEST_ACCEPTOR --principal TEST_ACCEPTOR_PRINCIPAL --roles TASK_ACCEPTOR
```

管理员负责配置和登记完整验收集合；执行者只能提交其被分配任务的候选，QA/Security
只能按各自正式审核分配操作，验收者只能验收。任一主体都不会因具备任务角色而取得
`TASK_CENTER_ADMIN`。

真实管理员凭据、持久权限和部署目录须由 Owner 对准确目标另行确认；本次交付没有
生成这些真实值。

## 启动、健康、停止、日志

前台启动便于观察和安全停止：

```bash
python3 scripts/task_center_app.py \
  --db /ABSOLUTE/TEST/DIR/task-center.sqlite3 \
  --test-authority-key REPLACE_WITH_TEST_AUTHORITY_KEY \
  --tenant tenant-test --host 127.0.0.1 --port 8765 \
  --model-master-key-file /ABSOLUTE/TEST/DIR/model.key \
  --test-identity-file /ABSOLUTE/TEST/DIR/identities.json \
  2>>/ABSOLUTE/TEST/DIR/web.log
```

- 登录入口：`http://127.0.0.1:8765/login.html`
- 健康：`curl --fail http://127.0.0.1:8765/healthz`
- 就绪：`curl --fail http://127.0.0.1:8765/readyz`
- 停止：向该前台进程发送 `SIGTERM`，等待标准输出出现 `STOPPED`；不要盲杀其他进程。
- 默认 worker/真实出站：`DISABLED`。仅获准 loopback fixture 时才可显式加
  `--allow-loopback-fixture-outbound`；该标志仍不授权真实账号、付费 API 或公网目的地。

没有安装 systemd、nginx、TLS、DNS、防火墙规则或隧道，也没有新增常驻服务。

## 登录与页面操作

登录后服务端签发 HttpOnly、SameSite=Strict 会话 Cookie；CSRF Cookie 不具备身份
授权能力。退出在服务端撤销会话。所有管理操作仍由服务端检查租户、角色、Writer、
版本和业务门禁。连接密钥只提交服务端，投影只返回掩码；默认禁止真实出站。

任务页面的资产查询只提交 `asset_key`；服务端查询 `CANONICAL_DB`、派生结果和摘要，
不再接受页面自报 `REGISTRY` 结果。旅程为：创建任务 → 查询受控资产 → 形成派单门禁
→ 领取/进展/检查点 → 候选/独审/验收；执行与审核需要各自登录主体，不能自批。

OAuth 页可配置固定 issuer/endpoints/redirect URI 并生成 PKCE 流程；回调占位页明确
`待真实授权`。本包没有真实 OAuth 客户端、grant 或外部换令牌验证。

## 数据、回滚与未完成

- 只允许使用新隔离 DB。旧 3 项 SQLite 迁移对空白新库不适用，未在业务库执行。
- 回滚：先安全停止进程，保留日志和 DB 作为失败历史，再恢复上一冻结归档；不要对
  业务库运行回滚 SQL。
- 当前无已核准的受保护远程入口、生产统一身份适配器或服务器现场参数，因此没有
  部署到服务器。Owner 从其他设备访问仍需另行批准准确的现有受保护代理/入口配置。
- 实际浏览器是否通过见同版证据；CLI/HTTP/Node 不能替代浏览器 E2E。
