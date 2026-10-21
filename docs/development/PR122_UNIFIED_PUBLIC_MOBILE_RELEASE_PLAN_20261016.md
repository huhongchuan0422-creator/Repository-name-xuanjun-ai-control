# PR122 公开展示与社区手机体验：统一候选及受控发布计划

## 精确继承

公开表达源 e654af3a6a0d59f34b27bbbf8ba3518783c6f719 / 独审 #6217671312 / 静态TAR 6d641401eb9212d3a6745f07bdf9b8a845aaaeb9fbf03542a8b63eafc38a4d19。

社区手机源 790937a5c96afcf3b3660e36cf36cfaab2002a72 / 独审 #6217103876 / 手机TAR c24c657ebb101a1a26b56ed2dcd510c676e02d43c1f9dcfbceed9cd28c166d9f。

两项源码审核继承。公开展示制品独立复算限制由审核方对本次组合实际Artifact补验，不用开发方复算替代独审。

## 本次组合变化

仅添加原审手机包9个文件，逐字节保留；核对原模拟app依赖哈希。中文、英文与默认社区角色选择页的消费者、商家、社区、分账方和平台入口均接同一准确手机版本；英文入口保留现有「角色演示为中文」说明。原测试路径及未接通SaaS入口保留，不启用新支付或后台。

组合清单1,288个公网站点文件，416个overlay文件，原始固定源新增101个路径；459个归档成员，458份包Manifest绑定。对比已审公开展示包，变化仅为9个手机文件、3个角色入口、两个原Manifest、source-pin，以及新增COMPOSITION_MANIFEST；Runtime与发布器字节不变。

新增组合器是离线候选构建工具，无apply、sudo、root安装或生产切换入口。输出明确REVIEW_ONLY。

## 目标基线与只读观察

目标主机 iZvt5t8tlrm8oiZ；当前预期 /var/www/wenwenwenyiyiyi.work/releases/pr122-hub-experience-ca7ab933-r2。

原生产事务 pr122-hub-experience-20261016-r2。当前文件以原b66eba8c静态包的1279文件Manifest核验，不能复用更早1277文件基线。

国内Runner只用githubrunner普通身份读取公开站点、Nginx配置哈希及systemd选定状态；不读取私有密钥、环境或客户资料，不调用客户中心root通道。当前receipt受保护，准确SHA及状态必须由Owner-root只读回执补齐，不通过权限绕过获取。Nginx磁盘源核对不冒充已加载进程验证；Runtime元数据不冒充内核沙箱验证。

## 拟定单次生产事务

拟用事务 pr122-public-mobile-20261016；拟用release pr122-public-mobile-reviewed。仅名称预留，尚无执行许可。

申请正式许可前应冻结：组合准确源码/Tree/CI/Artifact、全部Manifest和制品哈希、当前receipt SHA/current/1279文件基线、Nginx完整源哈希、Runtime验证、受保护发布包装及Host Pins。原发布器固定计数449/1279/92不能直接用于459/1288/101组合包，不得修改已消费许可或盲目调用旧apply。

## 发布与恢复顺序

1. 新包装继承既有受控事务锁、Owner-root路径信任、准确Gate、过期/撤销/单次约束及旧站漂移检查。实现差异绑定当前静态r2回执、数量及本次制品，独审确认后才可执行。
2. 保存1279个旧站文件、两份原CSP元数据及全部实际Nginx源配置，回读逐文件验证，备份hash记入新事务。保留所有r1/r2旧事务和备份。
3. prepare新独立release，不覆盖旧目录；验证1288文件Manifest、CSP及原模拟Runtime身份、沙箱、双会话隔离，不安装/停止/替换Runtime。
4. Nginx只补固定新手机路径，保留原规范URL /about，不开放任意HTML或私有路径；先nginx -t，再作激活前漂移检查，切current与reload。
5. 验收原菜单、双语、ICP、优惠表格、6000→2400→1200、90%/50%、手机角色跳转、两个广告位、旧深链、错误路径、JS/CSP、真实HTTPS与320/390/1440px。
6. 失败或未知结果进入HOLD_PARTIAL，保留现场，不自动重试。仅经同事务批准的rollback恢复旧current与原Nginx，核验旧1279文件及全部配置哈希，保持原Runtime不变；恢复后仍做HTTPS浏览器验证。没有备份验证或发现外部漂移时停止而非猜测恢复。

## 当前禁止项

尚未签发新生产许可；禁止复用已消费的#6216329680等旧许可。客户中心安装、真实客户资料或密钥接收、真实支付、DNS、东京退役、动态展示机制root安装、英国及币安系统均不在本次范围。

## 验证层级

离线组合测试、Hosted真实Nginx、Hosted浏览器、国内普通用户只读观察、Owner-root只读回执、独立制品核验、正式单次许可和生产HTTPS验收分别记录。任何缺失保持PENDING/HOLD。

## Owner-root现场输入已取得（22:42回传）

Owner终端只读回执已归档 evidence/pr122-unified-release/OWNER_ROOT_READONLY.json。准确旧r2 receipt SHA256为2c7507be447676e1cbb6ed649198081850403020c9d1856733b0de0f1eec83a8，状态HTTPS_SMOKE_PASS_AWAIT_BROWSER、intent为空、备份已验证。Nginx测试PASS；master85106执行/usr/sbin/nginx且默认配置命令绑定；内存配置无法直接内省，不伪称可验证。Runtime UID62621/PID269238，BPF直附及有效进出过滤均存在，挂载命名空间独立。此为Owner现场回执，不冒充独审远程登录。

国内普通用户观察CI38916842426/Job117026376801及组合CI38916842527/Job117026379268通过。目标新Host Pins已绑定13个Nginx实际源哈希、旧1279文件Manifest及上述准确receipt，不沿用旧1277基线。

新脚本pr122_site_hub_unified_release.py沿用ca8d2dda既有静态事务包装，保留原冻结helper8c403aac和preflight6b6a8b5f；仅更新新Pins路径、459/458归档与Manifest计数、1288候选/1279旧站/1281备份成员计数、101新增路径、当前体验r2回执路径、独立操作类型PR122_PUBLIC_MOBILE_UNIFIED及组合Manifest绑定。旧发布脚本和旧事务不修改。

新操作类型必须使用新单次许可；原PR122_STATIC_EXPERIENCE和PR122_COMBINED_WEBSITE不能放行。组合制品中的PENDING_ROOT_RECEIPT是先前组合构建时的历史状态；本次发布权威绑定以准确Host Pins及Owner归档证据为准，不更写旧组合包制造相同哈希假象。

发布包装依赖完整旧源包SHA74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63，仅从原Owner受保护目录复用，不上传私有原始源包。包装不包含许可文件，也不自动部署。


## 2026-10-18：官网静态独立节点与五次受控续接候选

本节为新源码候选，未签发执行许可。以上单次许可、1279历史基线和旧事务记录保持原义，不能因新增代码自动扩大旧许可。

执行原则继承原记录PR122 #6249926385及治理文档提交9261a14591f8ec253dfbab2d49e38b5c5671ba6c。本节只说明官网静态独立节点实现，不另建规则，不绑定注册登录或SMTP，也不改变P2。

静态新profile为OFFICIAL_STATIC_ONLY_V1 / CONTROLLED_STATIC_WEBSITE_V1。复用原Coordinator单一持久账本、最多5次、原transaction.lock、Lease/Fence、已成功阶段检查点。新许可必须准确签名绑定18000秒窗口、源码闭包、静态内容包、当前受保护Host Pins及旧站证据；成功即终止，额度耗尽停止，源码变化须新轮许可。UNKNOWN先HOLD，只有原许可范围内可信只读对账满足安全条件才续接。

完整静态内容仍复用已审核1d02版本1288文件包，不重写其内容。FULL_STATIC_REVIEW_V1显式读取460成员/459绑定；旧格式默认459/458不自动升级。旧站数量从新Host Pins的previous_file_count严格读取；不能把历史1279或目标1288当当前实机观测。路径规范、成员类型、完整Manifest、逐字节哈希均保持强校验。

新的控制器源码另以固定22模块、23成员的REVIEW_ONLY源包交付。STATIC_SOURCE_MANIFEST绑定准确源码提交；其哈希须进入新受保护Host Pins。隔离入口先核验完整源码闭包，再预绑定固定scripts包路径，拒绝影子模块、外部同名包及未绑定缓存。此包不含私有配置、信任库、许可、用户资料或1288静态网页内容。

静态HTTP验收范围仅GET、内容哈希、安全响应头及404。原preview synthetic POST和业务E2E不在本静态profile中运行，业务验收保持PENDING；不能将静态HTTP通过表述为客户流程或生产浏览器验收。

仍需按最终精确候选的本地测试、独立增量审核、新Hosted结果和真实制品绑定分别记录。现场基线、运行时闭包、受保护交付、签名许可及实机浏览器验收未取得者均UNKNOWN，不以本地测试代替。


## 2026-10-18 官网显式 GitHub 双主体审批增量

Owner明确批准仅官网审批接线增加 `STATIC_GITHUB_DUAL_APPROVAL` 模式。该模式必须由准确计划和受保护配置共同选择；不把旧许可扩成五次，不在原验签失败时自动降级，不改变客户登录的独立审核门禁。

- 固定 GitHub 仓库数值身份 `1413132159`，Owner 数值身份 `332398908`，独审数值身份 `95597695`；独审与源码作者不同。仅原固定 GitHub API、拒重定向、限时和限长读取。
- 原Owner评论准确绑定独审评论ID与全文SHA及完整计划SHA；独审评论绑定准确源码/树/制品/CI、HostPins、当前基线、完整十阶段合同、五小时及最多五次。受保护配置保存双方全文锚；评论正文不能自授信任。
- 每次原 gate/recovery 重新核对配置、仓库、双方评论、源码树、制品和CI。双方任一评论改文（包括撤销）、删除、版本不符、API失败或过期立即HOLD；无第三条撤销评论要求。
- 复用原持久额度账本、flock、Lease/Fence、幂等已成功阶段和成功终止。原登录、旧Ed25519静态入口及业务范围不变。
- 新增模块纳入源码闭包；准确新Hosted制品必须重新绑定。官网内容与成功只读取证可继承，但新源码不能沿旧执行许可运行。
- `STATIC_GITHUB_DUAL_APPROVAL.json` 是需要Owner另行确认准确内容后部署的root受保护配置；本代码提交不部署它、不生成密钥、不配置凭据、不签发安装许可。已有只读GitHub凭据若不可用仍HOLD，测试身份和凭据不得部署。

此节是开发合同说明；真实主机配置、准确执行许可和生产验收均不由本节成立。


### Explicit PUBLIC_GITHUB static transport compatibility increment

The authenticated transport remains the default when github_transport is absent. PUBLIC_GITHUB is an explicit protected-configuration, full-plan, Owner-body and independent-review-body binding; missing credentials never trigger fallback. It reads no token and creates no credentials. The fixed repository's PR122 comments page (100 entries, one bound page, no pagination/redirect following) must contain both exact pinned comment IDs. Missing/moved/edited/deleted/revoked comments or malformed identities fail closed. Every phase/recovery authority boundary re-fetches that page and rechecks the original full-body anchors and local revocation configuration.

The explicit metadata_policy PROCESS_START_AND_RESTART re-fetches exact commit/tree, artifact and completed-success CI metadata at each process entry/restart. Later gates reuse that process's verified metadata plus the unchanged local source/bundle bindings. Artifact and CI are not described as immutable, and this mode does not claim to re-fetch them at every effect. Runtime revocation is through the two live approval records and local revocation list. A new exact permission must bind these semantics; old permissions do not expand.

The original real adapter's successful ten-stage path performs 59 gates (295 requests with the old five-GET transport). A comment-page-only substitution would still require 62 requests and is not sufficient for a nominal anonymous limit of 60/hour. PUBLIC_GITHUB consolidates only duplicate no-effect prechecks in the static adapter; it retains the final phase pre-effect authority check, post-phase authority check, activation checks and recovery checks, plus all local deadline/Fence/source/input protection. The measured complete path is 38 gates plus three initial metadata requests = 41 requests. The signed request_budget is exactly 54, including 13 calls of failure-convergence allowance. Before child initialization or stage effects, fixed suffix budgets are checked against the last actual response remaining quota and the process allowance. The process allowance is not a replacement for the persistent five-Attempt ledger.

The API allowance is not a reservation of shared outbound-IP quota. HTTP errors, 403/429, insufficient remaining quota, missing quota headers, redirects, timeout, invalid JSON, or changed authority hold execution. No credential fallback, IP rotation, or waiting for reset inside a running stage is allowed. Successful work does not imply all five attempts can be completed under any shared-IP traffic pattern.

Static standard-library execution no longer imports cryptography merely to load unused customer encryption/signature helpers: AESGCM, Ed25519 and Feishu cipher imports occur at their actual operations. Those actual operations still fail closed without their dependency; customer runtime validation, login requirements and cryptographic behavior are not relaxed. Public-mode tests must block all cryptography imports in a fresh process while exercising the actual source/authority path, and retain original authenticated/Ed25519/customer regressions.

A new process, including a recovery process, must pass the full 54-request admission budget again. The 13-call allowance is not a promise that a restart can proceed with only 13 remaining requests. Insufficient quota holds before effects; a later start is permitted only while the exact permission remains valid and all original recovery checks pass. No attempt count is reset.


### 2026-10-18：既有阿里云控制能力与官网接线边界（Owner要求永久写入原开发记录）

已存在的正常云执行链是 GitHub Actions → 仓库既有 Secrets 引用 → STS AssumeRole → SWAS RunCommand → DescribeInvocationResult。该通道不依赖 Owner 电脑在线；电脑离线、云浏览器未登录或当前工具没有 workflow_dispatch，均不能单独推出 RAM/SWAS 不可用。每次判断前必须先读取原入口、精确分支/动作门禁以及实际运行 job/step 的结果；工作流总体 SUCCESS 可能只代表 validate 成功、云 job 被 SKIPPED。

可继承证据：
- 原交接文：[ALIYUN_FOUR_HOST_EXECUTION_HANDOFF_20261017.md](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/18fe5456087472b75182ccf014b1e60ca356e7d7/docs/ALIYUN_FOUR_HOST_EXECUTION_HANDOFF_20261017.md) 位于原 PR99 已有分支；固定核查版本为 18fe5456087472b75182ccf014b1e60ca356e7d7，不能因本网站分支没有该文件就否认原通道。
- 历史四机成功执行：[run 38991455661 attempt 2 / job 117275780078](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38991455661/attempts/2)。已核实真正的“Verify four fixed hosts through STS and SWAS”步骤成功；此历史事实不等于当前官网已部署。
- 原入口为 PR99 分支上的 .github/workflows/aliyun-four-host-readonly.yml（固定只读 workflow_dispatch），另有准确 Owner 数字身份、PR99 HEAD 和动作标签绑定的受控任务。既有工具可对获准 PR 添加准确标签，正常触发能力并非只有 rerun；具体标签必须匹配相应已审任务，不能借用 PR99 标签安装官网。
- 原 secrets 名称 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET 由受信 Actions 环境读取。不得读取或公开其值，不重新配置 RAM、不创建凭据、不向 Owner 索要新 Token，也不把原四机权限扩大为任意命令权限。

官网当前状态与开发要求：
1. PR122 的 73454b6f 产品控制器与制品已有代码/Hosted 证据；该提交并没有新的 SWAS 官网完整交付/安装适配。旧 PR122 staging 仅是固定历史单次包的非 root 保管动作，不能当作当前安装入口。
2. 原 PR99 helper/事务/标签仅适用其准确任务，不更改 PR99、不重放已成功会话、不把云投递重试算成产品五次额度。未知 RunCommand 结果须按原投递标识只读对账，不得因重跑工作流或移除/重贴标签再次盲发。
3. 优先核对已存在输入与原私有交付路径。缺失准确 source、artifact、HostPins、plan、真实批准或受保护配置必须诚实 HOLD；不能发布一个只有 invoke、没有完整 inputs 却声称可上线的空壳。
4. 本轮先准备 DOMESTIC_STAGING_READONLY：仅固定国内目标及两处有历史证据的根内固定文件名元数据和摘要；普通 push/评论只允许代码测试。完整 helper 字节、HEAD、范围和云参数需要准确核定后才可显式触发。它不是安装动作，也不是生产验收。
5. 官网正式安装仍须原产品入口执行准确实时批准、固定版本/输入、五小时、最多五次持久账本、锁/Fence 与恢复检查。云控制能力不替代这些门禁；当前不得宣称新官网云通道已部署或现场已验证。

本节记录原云控制能力及当前缺口，不触发云任务，不签发执行许可，不公开私有 HostPins、现场原文或凭据。

### PR122 事件分支与网站源码分支必须分别绑定

原 PR122 当前真实事件分支是 `feature/stage5-next25-integration-20261015`，其基线 head 为 `3beb5db669ec0004a4d3ef278f5519e0100e4403`；网站已获准开发分支是 `feature/work-pr122-site-hub-integration-20261016`。两者不是同一 ref。不得把网站工作提交称为原 PR122 的真实 head，或假设在工作分支新增 pull_request 工作流即可由 PR122 标签触发。

本次只读取证接线采用两个明确绑定：真实 PR 分支仅安装固定工作流，PR_EVENT_HEAD 用于原 PR122 事件、Owner准确标签及当前 PR 的核验；READONLY_SOURCE_HEAD 是工作流正文固定的完整40位已检源码提交，用于 checkout 只读适配器与 helper。持久意图和后续查询同时绑定两者，不能混用 GitHub run.head_sha 与 checkout 源码 SHA。普通分支 push 仍仅运行本地模拟/Hosted 测试；实际云动作须真实 PR 上的准确事件和全部固定门禁成立。

原官网产品 `73454b6f973e073067de7afb7580c1ac709ede2f` 的技术审核与制品证据按其准确版本继承，不能由这次只读取证接线改称新产品版本或安装许可。不合并整网站工作分支、不修改原PR的base/head关系，不创建第二个产品任务。首次109a只读接线的 Hosted 39147246174 失败记录保留：runner 36项通过；helper fixture把 Hosted 非root UID错误映射到根祖先，已仅修测试投影，生产 helper 的保护不放宽。该工作提交不具备真实PR事件触发条件，禁止以其标签试跑。

### 2026-10-21：完整固定静态基线只读源码候选（未准入/未执行）

依据原PR122 #6320173363、连接方 #6320055601，仅新增 `tools/pr122_static_baseline_readonly.py` 及对应离线测试；不修改旧8文件探针、host_preflight、注册能力、工作流或事件。无参数生产入口只接受固定国内hostname与root身份；这项身份检查不构成执行许可，仍需原连接方按准确候选字节及一次性范围核准。

完整候选观察清单固定为20项：本站current和原preview Runtime current两个链接；原r2 receipt、installed publisher、原preview unit及原HostPins十三条Nginx文件，共16项有界摘要；原transaction.lock和候选pr122-public-mobile-20261016.attempts.json两项仅lstat元数据（不读取账本正文，不获取锁）。两个链接只准在原站releases根或原preview根内的受限pr122名称，验证目标目录及NOFOLLOW祖先，不枚举目录。receipt只投影固定状态枚举及intent空/未知存在标记，其他正文不输出；配置、publisher及unit只报摘要/元数据，不输出内容。

复用原安全读取模式：dir-FD、O_NOFOLLOW、普通单链接文件、固定Owner/权限、读取前后FD/名称身份及最终保留路径复核，拒绝越界/链接逃逸/替换/增长。单文件2MiB，总读取16MiB，路径/持有FD各至多256，20秒monotonic及进程alarm，JSON输出至多32768bytes；不创建文件、不取flock、不运行子进程或网络、不控制服务。普通读取可能更新atime；逐项稳定不等于全局原子快照。HOLD后不继续读余项，不自动重试。

inputs/source准确根未知时固定UNKNOWN_NOT_READ，不接受任意根参数、不扫描猜位置；对应previous manifest/完整public计数也保持UNKNOWN。Runtime活动/沙箱、已加载Nginx、Writer/Fence/锁是否空闲，没有本范围内原只读接口则UNKNOWN；lock/ledger存在不构成Writer空闲证明。本候选只补已获范围内的固定文件观察能力，不假称所有现场绑定齐全。由原保管方补确切roots引用后，如需新增读取范围，仍须准确范围核准，不能临时追加路径。

离线验证入口：`python -B -m unittest tests.test_pr122_static_baseline_readonly -v`，仅临时合成FD根和固定路径fixture，不运行真实collect。Hosted仅沿既有适用覆盖，本轮没有扩展工作流，新模块未被旧工作流显式执行时不得称已过Hosted。已有品牌包、原离线输入候选 #6319390111 与摘要 #6319403826全部复用；本候选不覆盖或启动旧客户中心，不是现场取证、安装或生产许可。
