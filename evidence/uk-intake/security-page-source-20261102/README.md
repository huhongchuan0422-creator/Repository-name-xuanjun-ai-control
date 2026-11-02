> Current native-integration delta supersedes earlier baseline integration notes: see `NATIVE_INTEGRATION_DELTA.md` and `CURRENT_NATIVE_CANDIDATE_MANIFEST.json`. No deployment or usable phone link is claimed.

# 安全输入候选 v1 — LOCAL_CANDIDATE / NOT_DEPLOYED

任务：SAFE_INPUT_ASSET_REUSE_KOREA_BINANCE_V1；2026-11-02 Owner 授权唯一 Writer 在本地并行写候选，韩国取回优先复用，取不到才最小重写。本目录新增独立候选，不覆盖原工程、不声称已合入英国框架。既有 ROLE_SKILL_LEARNING_RECEIPT=PASS 沿用。

## 已实际实现

- Python 3.6 语法兼容的无监听器组件 `safe_input.py`：原 host/原 Protected Store 明确适配端口；没有数据库、文件凭据库、密钥生成、SecretRef 明文读取或网络请求。
- 移动端原生 POST 表单，三个正式名称的字段均 `type=password`，没有脚本、遥测、外部资源、前端持久化；固定用途/版本，准确原 host 路由前缀可传入。
- 原认证主体/会话绑定；CSRF 与精确 Origin 验证端口；600 秒请求契约；原子一次提交端口；并发/过期/重复/取消/UNKNOWN 的处理和原结果查询。
- 输出不包含提交值；适配器原始异常不外传；不自动重试 UNKNOWN。提交已成功而刷新异常不能通过重交覆盖。
- 响应 no-store/no-referrer/CSP/frame 禁止等；不把响应头当实际 Nginx、CDN、APM、浏览器历史或截图无泄漏的证明。
- `allowedHosts=()` 精确传递（适配到原 API 应为 `[]`），没有增加任何外发域名或支付权限。

## 未实现 / 不能宣称

本候选**不是可安装服务**，未创建可访问链接。没有绑定真实 host/Store、没有浏览器凭据注入实现。`ready()` 为必接适配口，不是已核现场证据。测试 Oracle 只存在于 `tests/` 的内存中；不得作为生产存储或原框架适配器使用。

真实公网 HTTPS/WS、手机打开、设备配对/认证、Nginx 路由与日志排除、持久化/重启、原 Store 更新删除、真实 canary、浏览器安全消费均 NOT_EXECUTED。不能将这份源码、静态页面或隔离测试报为完整交付 PASS。官方 OpenClaw 2026.9.9 原生浏览器注入此前核为 `BROWSER_SECRET_INJECTION_UNSUPPORTED`；韩国自定义合同尚未取回，仍 UNKNOWN，不以原生结论否定自定义实现。

“前端无明文”准确口径：Owner 输入时，浏览器输入控件及受信任服务进程内存必然短暂持有输入值；本候选不将其显示、持久化、日志化或送给模型。不能声称内存从不出现明文或 Python 字符串可可靠清零。浏览器密码管理器/自动填充/回退缓存/截图/扩展仍要真实验证，autocomplete=off 不是证明。

## 文件与运行

```
python -B -m unittest discover -s tests -v
```

只运行隔离测试，不启动监听器、不接网络、不读取环境变量/配置/数据库/金融秘密。测试随机非敏感字符串只在内存断言，不输出。41 项用例覆盖定向失败流，结果见 `test-results.txt`；负向重启用例明确证明 test Oracle 不持久。Python 3.6 仅 AST 语法验证，非真实 3.6 解释器执行证明。

## 接线候选（未执行）

1. 把组件接入**现有**受认证 HTTPS host 的原专用路径（例如原有 mount `/openclaw`，并非已选定的新路由）。不把整个 Control UI、整站根或 18789 暴露公网；Gateway 保持 loopback。原 `/owner/`、`/task-center-test/`、社区预览路由完整保留。
2. 由现有路由层解析原生 POST；拒绝重复参数名、非预期 content type、超原 host 已批准 body 上限。认证身份必须来自现有会话，不可信任 body/query 的 owner/session 值。保留现有 TLS 1.2/1.3、HSTS、限速/并发限制，准确值现场核后记录，不擅自新增业务配额。
3. `ExistingHost` 接现有 Owner 认证、原始精确 HTTPS Origin、原 CSRF 机制和原安全响应层。CSRF 不是 Gateway token/setup code；永久 token 不可进入 URL/HTML。反代可信链必须严格，不能信任公网伪造 X-Forwarded-*。未知权限不可通过新账户/新 token 补齐。
4. `ExistingProtectedStore` 接原请求生命周期与 Protected Store。不存在普通公网表单直写数据库；不得直接使用韩国金融 Store 实例，不创建第二套库。适配器真实接口/类型尚未知，不猜 OpenClaw RPC 方法或 URL。
5. 所有秘密请求的 access/error/APM/CDN/WAF/代理/应用/工具日志须禁记录 body、完整路径、questionId、Referer、token；query 只用于原 ID 定位，不放 bearer。`/ask/<questionId>` 是 locator，不能据 ID 免登录。仅固定事件分类、状态码、无敏感随机运行关联号可作为脱敏日志候选；本模块自身不记录日志。
6. 一次提交必须在原持久事务/原有原子机制中校验当前身份/会话、用途/版本、服务端时钟、请求仍 pending/授权仍存活、原条目版本前提；成功写入三项 protected 值及 ref 与请求状态必须一致。原 Store 源码已证有批量事务；真正缺口是原 QuestionManager 内存回执。新增同原 DB 的 metadata-only 持久回执候选见 INTEGRATION_AND_MIGRATION.md，不能只用原内存 manager 当完整一次性恢复。
7. 未知消费/写入/锁状态先查原 attempt/receipt，不盲重放；原已确认失败恢复机制沿用，不能为了重试新造 permit。创建请求结果不明也查询原请求，不立即再建。
8. 成功后只让原 Store 元数据/SecretRef 出现于模型或任务输出。链接过期不删条目；原更新/删除继续通过既有 Owner 控制，SecretRef 生命周期与请求 TTL 分开；原软删除策略须准确说明，不能冒物理销毁。
9. 真实浏览器只允许经既有受支持、独立可信执行边界解析 SecretRef；不是把值填进 AI 工具文本参数。没有经过证明的消费者则保持明确 HOLD。`allowedHosts=[]` 期间不允许对外注入；必要时先核目标并最小化授权精确 hostname（本候选不设置）。

## 验收与回滚

仅本地候选无需生产回滚。以后获得明确部署授权仍须：原精确版本/配置备份、diff、语法/config 检查、受控热加载回执、原路由健康、精确恢复制品及恢复检查。当前未取得实际配置路径，不伪造 `nginx -s reload` 等可执行部署命令。

canary 必须先完成手机可达、10 分钟边界、一次性与并发、更新删除、链接过期后 ref 存在、日志/模型/工具/浏览器无泄漏、浏览器受支持消费、重启恢复、原服务/金融项目无回归。全部证据齐全才讨论最小接线候选安装，不以单个状态 STORED 代验收。

## 原资产映射与证据

- 韩国原根：`/opt/xuanjun-migration-s07/releases/korea-model-handoff-v1/app/`。
- `scripts/secure_secrets_portal_server.py` 85197 B / `57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1`。
- `ai_service/secure_secrets_portal.py` 71866 B / `3804d540281c0e07480e5c95ef98f800b498fd09e2f14966d9d3737830157ba7`。
- `trading_execution/secure_credential_intake.py` 24859 B / `0b602d99d50816cb1ff85c54823433e49a32413228f87c5e7ddc9278a2b20980`。
- 原客户多字段 Portal、会话目录0700/文件0600、文件锁机制存在；历史 build_service 两处 TTL=1800，社区目标600须最小适配。只借鉴已核机制，未复制不完整正文冒原件。两合同函数正文/消费者仍待取。
- 已读固定 OpenClaw secrets 文档 commit `bcfc88812a35243893585dbeca87ca41b48272ca`：protected-only 输入、原 run 权限、600 在支持区间内、值保留、写入后刷新失败不得重交、空 allowedHosts 禁 egress。此候选没有实现或假设其内部 RPC。
- 官方 browser-use/Vault/nginx/OWASP 固定来源与许可证、39 项学习隔离断言见既有 ROLE_SKILL_LEARNING_RECEIPT 与补充。本次新41项候选测试与学习测试分别统计，不冒现场验收。

## 与原资产差异

| 项目 | 原证据 | 本候选 | 未接项 |
|---|---|---|---|
| 页面 | 既有客户多字段 Portal | 原生三字段遮罩候选，适配原 mount | 原模板/框架取回后优先复用 |
| 请求 TTL | 原1800秒 | 常量600/原接口必接 | 真正服务端时钟与原生命周期 |
| 单次 | 既有锁/会话元数据 | submit_once 原子契约和竞争测试 | 真持久原子实现/崩溃恢复 |
| 存储 | 金融与 Operations Store 既有边界 | 不造库，仅 Protected Store 端口 | 原英国被批准 Store 绑定 |
| 浏览器 | 原生未支持，自定义未知 | capability 抽象端口，无明文 resolver | 真实安全注入证据 |

## 新增接线结果
原 Store API adapter、同库持久回执最小增量和准确验证层级见 `INTEGRATION_AND_MIGRATION.md`。三条真实原写kernel已在临时SQLite验证；整体仍非生产、浏览器SecretRef安全注入仍未完成。

独立审阅已关闭两个定点缺陷：questionId错行返回、原question取消但run仍活。末次durable增量31项独立复核通过；审阅未覆盖完整Gateway/迁移/真实日志链。
