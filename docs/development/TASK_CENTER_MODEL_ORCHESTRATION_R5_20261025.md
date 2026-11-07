# 任务中心后台与多模型统一调度 R5（TEST_ONLY）

> 历史 R5 启动说明保留作审计记录。当前后台测试版的服务端会话、默认关闭
> 出站及回滚步骤见 `TASK_CENTER_TEST_BACKEND_20261025.md`；不要再把下文临时
> Header token 页面当作当前使用入口。

## 定位与边界

本候选沿用原 `Supervisor`、`GatewayKernel`、SQLite、outbox、checkpoint、
Writer Fence 和七板块数字孪生。`tasks/events/outbox` 仍是任务事实唯一来源；
Provider、模型、角色、评测、请求、用量和动作门禁表只是同库元数据，不复制任务
终态。生产模型调用、真实云动作、P2/P3/社区/B5 接线均为
`NOT_IMPLEMENTED / NOT_EXECUTED`。

## 启动

先用既有 CLI 创建本地 TEST_ONLY 数据库，再生成两个仅本机可读文件：

```bash
python3 scripts/reusable_scheduler_cli.py \
  --db /tmp/xuanjun-task-center-r5.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  app-demo --tenant tenant-r5 --lock-root /tmp/xuanjun-r5-locks
python3 - <<'PY'
from cryptography.fernet import Fernet
open('/tmp/xuanjun-model.key','wb').write(Fernet.generate_key()+b'\n')
open('/tmp/xuanjun-admin.token','w').write('replace-with-local-random-test-token\n')
open('/tmp/xuanjun-actors.json','w').write('{"developer-1":"developer-token-123456","qa-1":"reviewer-token-123456","acceptor-1":"acceptor-token-123456"}\n')
PY
chmod 600 /tmp/xuanjun-model.key /tmp/xuanjun-admin.token /tmp/xuanjun-actors.json
python3 scripts/task_center_app.py \
  --db /tmp/xuanjun-task-center-r5.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  --tenant tenant-r5 --host 127.0.0.1 --port 8765 \
  --model-master-key-file /tmp/xuanjun-model.key \
  --admin-token-file /tmp/xuanjun-admin.token \
  --actor-token-file /tmp/xuanjun-actors.json
```

浏览 `http://127.0.0.1:8765/` 查看七板块投影；`/admin.html` 是管理后台。
后台进程独立于网页。模型队列可在另一个前台进程持续推进：

```bash
python3 scripts/model_scheduler_runtime.py \
  --db /tmp/xuanjun-task-center-r5.sqlite \
  --test-authority-key 0123456789abcdef0123456789abcdef \
  --tenant tenant-r5 --model-master-key-file /tmp/xuanjun-model.key
```

停止方式均为对应前台终端 `Ctrl-C`。没有安装 systemd、后台常驻服务或生产入口。

## 服务端契约

### 提供方、模型、角色和成本

- 每租户最多 10 个提供方；支持 `siliconflow` 与明确的
  `openai-compatible` 适配器，其他协议必须新增独立适配器。
- 适配器真实解析成功、401、429、5xx、超时、协议错误和 token 用量；超时或
  Worker 丢失后状态为 `UNKNOWN`，不会盲重试可能已有副作用的请求。
- `KNOWN_FREE / KNOWN_PAID / UNKNOWN` 分开；价格未知从不按零成本处理。
  未明确允许付费时只选已通过实际 TEST_ONLY 评测的免费模型。
- 排序先满足能力和评测，再按已知免费/已授权付费/未知价格及评测中的质量、
  耗时、重试、返工数据选择；不是只比较 token 单价。
- 版本化角色分 `EXECUTOR / REVIEWER / ACCEPTOR`；审核与验收角色没有 Writer，
  同一主体不能自审或自验。Skill 只接受带 64 位审核摘要的 `APPROVED` 绑定。

### 密钥

- API 密钥只通过受管理员令牌保护的 POST 进入服务端，以 Fernet 加密后存入同一
  SQLite；主密钥和管理员令牌来自权限必须为 `0600` 的外部文件。
- GET 投影只返回尾四位掩码；源码、日志、审计、前端存储和导出不返回明文。
- 替换会递增配置版本；停用会阻止新调用并取消尚未运行的队列项。
- 本包未配置或调用任何真实密钥、真实账号或付费模型。

### 长任务与恢复

- `model_requests` 持久保存幂等键、任务/attempt/角色、payload 摘要、尝试次数、
  Worker lease、心跳、checkpoint、取消请求、结果和错误。
- 页面关闭不影响独立 scheduler；重启读取同库。到期的 `RUNNING` 被收敛为
  `UNKNOWN/WORKER_LOST_SIDE_EFFECT_UNKNOWN`，不会自动换模型重复有副作用调用。
- 只有明确 429 在配置上限内退避；超时、断连和其他已可能送达的传输异常均进入
  `UNKNOWN` 对账，不自动重放。并发、每分钟真实调用尝试限速和三次失败熔断
  在服务端生效。撤销当前任务权限或停用 Provider 后不再发起新调用。

### 项目、执行门禁与审核闭环

- 项目快捷入口在原 Gateway 注册任务，并持久绑定交付阶段、小功能、目标、范围、
  验收、依赖、资产版本和唯一责任方；复杂图继续使用原 `REGISTER_GRAPH`。
- `ExecutionPolicyGateway` 要求资产/能力预检。`UNKNOWN` 不能解释为不存在，也不能
  据此新建资产或通道。
- 历史能力、只读连接和当前写授权分开；只有未过期的
  `CURRENT_TEST_ONLY` 写授权，且该授权严格绑定 task、attempt、资产版本和 Writer，
  才可让动作申请进入 `ADMITTED_TEST_ONLY`。进入仍不表示
  外部动作已执行。
- 模型只能提出动作申请；服务端重查可信租户、task/attempt、资产版本、动作范围、
  当前授权和唯一 Writer。范围扩大必须绑定独立审核通过的变更单。
- 候选冻结后，独立 Reviewer 可一次提交缺陷并形成返工状态；返工必须提交不同
  artifact 的新候选，旧候选和追加审核历史不可覆盖。Reviewer 通过后，另一个
  Acceptor 才能验收并通过原 Gateway/Fence 安全撤权形成 canonical `SUCCESS`。
  执行者不能自批，Reviewer/Acceptor 使用独立服务端主体令牌而非请求体自报身份。

## 只读投影修复

`GET /api/projection` 和管理员 GET 使用 SQLite URI `mode=ro` 与
`PRAGMA query_only=ON`，在活动 WAL 下读取最新提交；不会实例化 Supervisor 或
Gateway 的建表/迁移路径。缺库/缺表明确失败。任务/项目 hash 路由对每个路径段
执行对称编码和解码，普通、中文、空格与含斜杠 ID 均能往返；非法编码拒绝为
`invalid` 路由。

## API 操作与身份

所有入口需要本地管理员令牌；提交、审核、验收和变更审核还必须同时提交由服务端
0600 映射文件配置的独立主体令牌。主体令牌只保存在当前页面内存，服务端把它映射
为可信 principal；请求体中的姓名不能替代认证。

`UPSERT_PROVIDER`、`DISABLE_PROVIDER`、`UPSERT_MODEL`、`CREATE_ROLE`、
`BIND_SKILL`、`REGISTER_BENCHMARK`、`RUN_BENCHMARK`、`CREATE_PROJECT_TASK`、
`REGISTER_GRAPH`、`START_TEST_ONLY_TASK`、`ASSIGN_ROLE`、`QUEUE_REQUEST`、
`CANCEL_REQUEST`、`RUN_SCHEDULER_ONCE`、`SUBMIT_CANDIDATE`、
`REVIEW_CANDIDATE`、`ACCEPT_CANDIDATE`、`SET_MODULE`、`RECORD_PREFLIGHT`、
`ADD_TEST_AUTHORIZATION`、`PROPOSE_SCOPE_CHANGE`、`REVIEW_SCOPE_CHANGE`、
`REQUEST_ACTION`。

这些入口只接受 TEST_ONLY 环境；不存在生产 Dispatch、真实暂停/恢复、支付、账号、
OCR 识别或云操作。

## 测试与未执行项

新测试覆盖隔离 HTTP 的正常、401、429、超时/迟到和价格未知，双租户、10 个
Provider 上限、能力评测、免费优先、并发/限速/熔断、幂等队列、页面关闭后的
独立进程、重启恢复、撤销/停用、唯一 Writer、资产预检、授权/版本/范围门禁、
独立审核返工与完整项目旅程。实际命令、原始 stdout、退出码和测试标识清单随
交付包提供。

- 真实浏览器点击/截图：`BROWSER_UNVERIFIED`。
- 真实 Provider/API 密钥/付费调用：`NOT_EXECUTED`。
- 生产部署、分布式锁、生产 Executor、P2/P3/社区/B5 接线：`NOT_IMPLEMENTED`。
- 旧迁移环境相关 3 项：继续 `NOT_EXECUTED`。
- 历史 R4 日志的 181 次 Python 执行只对应 136 个不同测试标识；不得写成 181 个
  不同用例。
