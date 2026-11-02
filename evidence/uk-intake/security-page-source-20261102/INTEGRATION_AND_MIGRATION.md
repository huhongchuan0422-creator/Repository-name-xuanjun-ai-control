# 原框架最小接线与同库回执候选（不执行部署）

## 1. 真实用途与终点

Owner 在手机填写社区后台验收 URL/用户名/密码 → 英国现有 Protected Store / SecretRef → 原授权验收浏览器安全注入并实际登录 → 后台页面核对测试。不能以已存入、UI预览、一次登录或一次调用冒全部验收。业务后台缺验收账号，不是英国对话403复发；本候选不创建或重置高权限账号。

## 2. 原实现精确证据

原 npm 制品 `openclaw@2026.9.9`，package.tgz SHA256 `a46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7`；原 LICENSE 为 MIT，摘取源码保留 LICENSE 和清单。

- `secret-store-CuSJMUWv.mjs` 行65–133：`writeSecretStoreEntriesInternal` 单次 `runOpenClawStateWriteTransaction` 中批量插入/更新。行155–157公开封装 `writeSecretStoreEntries`，export alias `l`。这已支持三条值的批量事务，不再虚设“Store不支持三项原子”阻塞。
- 同文件行207起 `toMetadata`：`secret` 不回传值，`env` 有 valuePreview；候选只写 secret 且元数据白名单，不扩散 env。原 `listSecretStoreEntries` alias `r`；原删除 `deleteSecretStoreEntry` alias `n`，软删除而非物理销毁。
- 原每条值最大65536 UTF-8 bytes，这是既有技术限制，不是新配额。原 SQLite 静态未加密，受0700/0600保护；“API不可读回”不等于主机管理员无法读取。不擅新增加密主密钥。
- `question-2U20Yooq.mjs` 行620–697 的原 `question.resolve` 仅从首个 store-bound question 接一个值，调用原 manager.resolve(commit)，再 reload。仅简单接三个普通请求不能冒一次多字段统一提交。
- `question-manager-27btsO43.mjs` 行161–168：原 manager 先同步 commit，再把内存状态标 answered；容器为 process-local Map，终态15秒清理。原 Store batch commit 不等于持久请求回执。独立审阅已复现此差异。
- `openclaw-state-db-transaction-V9_-0J3N.mjs`：只有原 managed transaction 可被复用；`sqlite-transaction-BHOCk0oF.mjs` 行230–246 在同连接已有事务时用 SAVEPOINT。不得从普通 BEGIN 绕原 admission。

## 3. 实际新增候选文件

- `openclaw_store_adapter.mjs`：真实原 Store write/list API 组合；元数据白名单与 SecretRef provider 回调；原 question.resolve 多字段扩展位置示意。**其单独 resolveAcceptanceBundle 仍依赖原内存 receipt，不能单独作为最终一次性提交路径。**
- `durable_receipt_adapter.mjs`：新的提交路径候选；在原 shared-state DB 内增加一个**仅元数据**的 `safe_input_request_receipts` 表。原 secret_store_entries 完全复用，不新增凭据库，不修改 updated_by 审计含义。
- `safe_input.py`：框架无关的表单/边界契约实现与测试。不启动 Python 服务，不提出第二框架；最终页面放回原 Control UI/原 host 页面组件，本文件可作为模板/接口测试基线，不应单独安装成公网服务。

## 4. 同库回执最小增量

`MIGRATION_SQL` 仅是候选，位于 JS 文件常量。字段只含 request_id、原 Owner ID、原会话非凭据标识、用途、UI版本、创建/600秒到期时间、状态、提交时间；不含 URL/用户名/密码/CSRF/token/secret值。

流程：
1. 原 Owner 身份/CSRF/Origin 验证，原请求/run仍有效。由原 request metadata 注册 request_id 与用途/版本/会话，不接受客户端任选绑定。
2. 进入原 `runOpenClawStateWriteTransaction`；同一连接读取回执并验证 Owner/会话、pending、过期、原run有效。
3. 原 `writeSecretStoreEntries` 使用 `{ database: state }` 加入**同一受管理事务**，三条均 secret + allowedHosts=[]。
4. 同事务将回执标 COMMITTED，外层提交后才回 STORED。回执更新失败则三条原写入一并回滚。
5. commit后进程中断：新进程可以查询原库 COMMITTED；重复同request不写，不依赖15秒内存。未知结果先查原回执。
6. 过期/取消仅影响请求，不删已保存ref；后续合法更新/删除保留历史提交回执。历史 STORED 不声称当前ref仍存在或内容未更新，应另查当前元数据。
7. 原 runtime reload 在事务外做，失败标 STORED_REFRESH_PENDING，不撤销已提交状态、不允许重放。

使用新表的原因不是偏好“再加一层”：当前原请求仅内存，跨进程结果查询确有缺口；不误用 updated_by 当回执，也不新建凭据库。

## 5. 迁移与回滚边界

- 必须先核现安装 schema version、原 canonical table registry / migration API，再为上述一张表登记下一**实际**版本；当前版本未知，不编造迁移序号，不直接在生产 CREATE TABLE。原 schema admission 可能拒绝未登记表，隔离SQLite通过不消除此风险。
- 部署候选需原源码分支/commit、原 schema snapshot、备份制品、向后兼容读表与回滚版本测试。代码先停止新增请求，再等待原在途结束或逐项取消。回退到旧代码不能删除已有 secret 值，也不能把已消费请求重新置pending。
- 优先回退代码保留 metadata-only receipt 表供查证；表若必须删除需另有保留回执方案并遵守Owner授权。不能简单 DROP TABLE 后宣称一次性仍成立。
- 本轮只在临时隔离 SQLite 上创建/删除测试夹具，没有生产变更，没有生产回滚需要执行。

## 6. 隔离证据的层级

- Python边界/页面契约：41项（内存oracle，非生产）。
- Node adapter orchestration：12项（回调替身，非真实Gateway）。
- 原 write/delete/metadata 函数正文 + 原 bundled Kysely 编译器 + 真实 SQLite：11项。测试包装替代了schema admission/transaction初始化；metadata list使用受限SELECT再调用原投影、未运行完整原list与脱敏注册链。**不能称完整原 Store/Gateway 已执行。**
- 同库回执候选 + 同一原writekernel + 真实SQLite：31项，包含实际close/reopen、原secret写与receipt标记一起回滚、模拟commit后断开再查、重放不覆盖、更新删除后保留历史receipt。崩溃是确定性注入，不是OS kill/断电测试；多进程并发尚未实测。
- 原模块完整导入尚未执行：本地原制品没有随包提供 `@openclaw/fs-safe`、tslog、json5 等所需依赖。没有为此安装依赖，不把kernel测试冒充完整应用。
- 移动端渲染实际启动 Chromium 被当前沙箱 socket 权限拒绝，未有截图/手机浏览器结果。`preview-disabled.html` 仅本地无秘密不可输入预览，非安全链接；无公网发布。

## 7. 浏览器注入：明确未完成及最小必要原框架提案

固定原版源码：
- `form-fields-B9V6H6db.mjs` 行14–35 只支持 ref/type/value，拒绝 secretRef key/object value。
- `browser-tool-description-DsnF2LXy.mjs` 行166–202 type.text 为 string，没有SecretRef参数。
- `pw-ai-CXSFycyo.mjs` 行288–314 `fillFormViaPlaywright` 直接 locator.fill(value)，没有Store resolver。
因此原生是 **BROWSER_SECRET_INJECTION_UNSUPPORTED**，这不能通过表单或Store写入解决。韩国自定义原实现合同未知，不抹掉它可能存在的支持。

最小必要候选（尚未实现/安装）：在**原 browser executor 的受信任边界**新增引用型凭据填写/登录内部操作，参数仅为三条固定 SecretRef、已授权用途与目标页面/版本、原权限上下文；原Store在该边界解析，秘密值绝不进模型工具参数/结果。不是新起浏览器系统，也不是把明文作为 browser.type 参数转发。

必须具备：
1. 使用Owner批准的实际验收账号；不得新建/重置高权账号。目标 URL 也可能含秘密，不能返给模型/日志。
2. 初始 allowedHosts=[] 时硬拒绝外发/注入。核实原社区精确 HTTPS hostname 后才按已获权限最小绑定；跨域redirect/iframe和不匹配证书不可接收。
3. 输入阶段抑制 DOM快照/屏幕/trace/网络body/控制台等模型观察通道；输入控件与页面回显中的秘密不能仅凭type=password当作安全。
4. 登录后页面核对必须通过经过验证的受信任脱敏观察/断言结果通道。不能把原始DOM或截图交给模型后再声称“会脱敏”；截图/Canvas/URL/用户名回显需逐项验。
5. 有效身份/授权、同run结果、错误与恢复验证，失败不能回退到明文工具填充。

以上是最小安全机制变更提案，不是已支持声明。支持机制未实现/未证时，完整交付保持 HOLD，不采集正式账号；可继续本地无敏感canary验证页面/Store/回执。

### 本轮独立审阅定点修复
1. metadata(questionId) 返回另一个同Owner请求时，页面/提交/结果全部拒绝。
2. 原 question 已取消但原 run 仍活时，register 与 submit 都重新核 pending 和完整绑定，拒绝写入。
3. receipt 查询保持 Owner+原会话绑定；没有默默扩成新会话可读。跨新会话恢复需原host现有权限政策核实，不自授。

浏览器安全注入、生产迁移/host适配、手机真实渲染未验仍为具体缺件；本地测试通过不解除这些限制。

## 8. 原框架实际修改位置（候选，不能直接修改已装 dist）

| 原源码/制品证据 | 函数/作用 | 所需最小接线 |
|---|---|---|
| `src/gateway/server-methods/question.ts`，打包 `question-2U20Yooq.mjs` 行359起 | `createQuestionHandlers` / `question.request`、`question.resolve`、`question.get` | 注册固定社区bundle用途/版本/三名称；复用原session/run权限；resolve commit 内调用同库durable adapter；get可查持久receipt但保持原Owner/session权限。不是另增未认证RPC。 |
| 同文件 / `src/gateway/question-session-access.ts` | `withPreparedQuestionSessions`、`prepareSelectedQuestion` | 保留原授权/访问revision/生命周期检查，不用新布尔grant代替。 |
| `src/gateway/question-manager.ts` / `question-manager-27btsO43.mjs` | `QuestionManager.resolve`、pending/expiry/cancel 与广播 | 原回执广播保持；持久commit已完成却广播/refresh失败时查同库receipt，绝不再写；pending取消同步到durable或每次重新核原状态。 |
| `src-D2gvuSyP.mjs` 导出的 `validateQuestionRequestParams` / `validateQuestionResolveParams` | 原协议校验器 | 需要原源树中对应schema的固定bundle字段候选，字段白名单不能放任任意secret名称；源文件具体路径尚未在该本地摘件中定位，不猜。 |
| `src/secrets/store/secret-store.ts` / `secret-store-CuSJMUWv.mjs` | `writeSecretStoreEntries`、`listSecretStoreEntries` | 复用批量写/当前元数据，不新增secret value读API、不改原审计身份字段。 |
| `openclaw-state-db-Dh2awMJ8.mjs` | `runOpenClawStateWriteTransaction` alias l | 同原state handle，原admission和嵌套SAVEPOINT；新receipt与三原值一起commit。 |
| `openclaw-state-db-readonly-BUOubhzc.mjs` | `withExistingOpenClawStateDatabaseReadOnly` alias f | 仅receipt元数据查询；不是 state-db模块的f导出。完整readonly实现本轮未执行。 |
| `openclaw-state-db-legacy-backfills-BSKqroDt.mjs` 原 `OPENCLAW_STATE_SCHEMA_SQL`，`openclaw-state-db-existing-schema-DXYsEyhD.mjs` 原版本迁移，`sqlite-schema-contract-htlQbbqu.mjs` 原schema校验 | canonical schema / versioned migration | 同库新增一张无秘密receipt表，纳入真实版本迁移和schema registry；不得直接注入未知table后绕schema拒绝。当前生产version未核。 |
| `extensions/browser/src/browser/form-fields.ts` / `form-fields-B9V6H6db.mjs` | `normalizeBrowserFormField(s)` | 原值型填写保留；新的SecretRef输入应独立类型且只能进入原可信executor，不让模型把ref先解析成text。 |
| `pw-ai-CXSFycyo.mjs` | `fillFormViaPlaywright` 行289起及其原调用路由 | 原受控browser边界解析/填充/登录操作，抑制观测通道直至可信脱敏；与原路由权限和目的地校验一起改。未实现支持。 |

新增 `browser_ref_policy.mjs` 为本地负例策略候选，12项测试覆盖[]禁止外发、错误Ref、跨域/iframe/HTTP/userinfo/端口变更/通配host拒绝、未支持消费者与未证明观测边界拒绝。它没有解析秘密、没有启动浏览器、没有实际注入；即使条件齐全也只返回 POLICY_ONLY_NOT_INJECTED。真实注入仍 **BROWSER_SECRET_INJECTION_UNSUPPORTED / 现场自定义 UNKNOWN**。
