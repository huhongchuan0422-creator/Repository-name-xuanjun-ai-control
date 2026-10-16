# PR122 动态作品展示接入约定

沿用原仓库、PR122、国内官网及既有 Release Gate。本文是接入和发布机制的候选，不是生产安装回执。

## 官网与职责

Work 维护首页、一级导航、栏目归属、展示接入和发布通道。ChatGPT 维护二、三级业务页面、功能、内容和测试。原三个一级入口继续保留；首页的产品、可视化、作品进展、共创生态和客户交付各有清晰入口。新增机制不替代现有官网。展示概览页直接复用已绑定的实际官网 header、footer、语言系统和交互脚本；五个数据视图属于内部栏目，不替换原一级导航。

五个数据视图使用同一组已审核记录：

| 视图 | 路径（待接线） | 进入条件 |
|---|---|---|
| 成熟案例 | `/showcase/cases/` | 项目快照匹配验收记录，必需里程碑均有已审核 DONE 证据 |
| 开发中项目 | `/showcase/projects/` | 项目登记通过内容审核，状态 DEVELOPING |
| SaaS 市场 | `/showcase/modules/` | 注册定义、模块包、双币有效报价、成本证据和上架审核一致 |
| 产品路线 | `/showcase/roadmap/` | 已审核项目及里程碑，按记录计数，不虚构百分比 |
| 共创生态 | `/showcase/ecosystem/` | 已审核贡献/活动记录，规则仍引用权威生态页面 |

独立项目详情固定为 `/showcase/projects/{project_id}/`。项目继续使用原详情 URL；成熟版本另外保留 `/showcase/cases/{project_id}/` 的稳定详情。中文与英文概览分别位于 `/showcase/`、`/showcase/en/`。现有 `/marketplace/`、`/visual/`、`/ecosystem/` 和客户权限入口继续保留。

## 登记和自动发现

项目记录存放于 `showcase/projects/{project_id}/*.json`。版本为正整数，已提交版本不可原地覆盖。新增版本使用新文件和新目录；项目间 ID、页面和版本互不覆盖。

开发方在原集成分支按项目目录贡献二、三级页面和声明，保持彼此目录隔离；原 native 开发分支可继续保留。接入数据不要求 Work 改中央菜单。开发方可用 `python -m scripts.pr122_showcase_register --help` 登记 project/page/module。该工具生成待审记录并计算页面及整包资源哈希，不会发布。也可以按本目录真实 JSON 示例生成记录。每条记录必须有中文、英文标题和说明。

新增页面使用：

`showcase/projects/{project_id}/views/{page_id}/v{version}/public/`

其 index.html、CSS、JS、图片和字体全部绑定在页面声明的资源快照哈希中。发布 URL 自动生成，项目导航从获审声明自动生成。保留旧版本目录可保留旧深层链接；撤销记录会阻止相应版本继续进入新快照。

页面必须自包含，使用外部 CSS/JS，不使用内联脚本、事件处理器、style 属性或 base 标签。每包最多 1,000 个文件，单文件最多 8MB。禁止符号链接、隐藏文件和非公开配置。不能把客户私有资料放入公开源码或 public 目录。HTML 文案转义，公共输出不包含待审队列、私有声明、成本库或凭据。

## 记录类型和进展

project：项目简介、场景和必需里程碑。page：角色入口及页面/资源哈希。milestone：PLANNED / IN_PROGRESS / DONE 和 GitHub 证据链接。acceptance：获验收的项目版本、完整展示快照哈希及精确版本成员清单（members）。已验收案例保留该稳定快照；后续新版本开发不会抹掉成熟案例，案例详情与当前开发详情分开。module：原注册表模块标识、封装包哈希和演示入口。ecology：公开昵称、贡献或活动说明。

只有 PUBLIC 且经过外部审核的记录可公开。作者自行填写 approved、PASS 等字段会被拒绝。新版本未审或尚未部署时继续选取保留的已审旧版。未审页面不进入项目导航。

完成数只统计项目声明的必需里程碑中已获审的 DONE；总数取必需里程碑，不把缺少记录当作完成。没有验收记录，或验收快照与当前项目、页面、里程碑不一致，不转成熟案例。实际开发记录与审核仍由负责方提供，程序不会从提交次数猜测完成率。

首个项目是社区分账。当前登记六项仍待完整验收的里程碑；不把它标为成熟案例。新商家页面复用既有获交付界面，仅将资源调整为独立包并外置样式，保留三个模拟商家及其明确提示。消费者入口复用已实机核对的 r2 页面；其来源映射单独冻结。其他客户角色由 ChatGPT 继续交付，旧测试工具不被误标为新的客户产品界面。

## SaaS 和业务规则

复用 `community_saas_modules.catalog()` 与现有 offer/cost 服务函数。已有七个注册模块自动进入登记发现；新增封装模块由开发方在原注册定义或 module 声明中提供标识和包，不需要 Work 手写商品网页。登记待审不等于上架。模块记录必须声明双语准备材料/条件（明确不需要时为经审的空列表）；内容公开审核不等于商业上架。独立内容审核回执还需把获准上架的模块对象哈希明确列入 module_admission_sha256，随后才与有效报价和包绑定共同准入。模块列表及独立详情页自动生成，代码作者的自报状态不产生上架资格。

价格适配器只读访问既有权威库，校验原有表结构，读取 EFFECTIVE / PUBLIC 报价并通过成本证据检查。人民币和美元分别保留原生最小单位，不推算汇率，不将 UNKNOWN 变为 0。月付、年付、买断、免费等方式来自原 offer 模式。演示购买保持未开放，接入审核通过的真实购买服务后才能启用。

生产权威报价库或其受控导出通道尚未接线时，市场可以如实为空，不能用测试价格补齐。测试中的 100元/19.90美元仅为 SQLite 测试夹具，不是实际售价。

生态规则引用 `DEVELOPMENT_V27_ECOLOGY_V11_20261014.md`，特别是 7.7.15B 与 6.6。新增展示不建立第二套余额、报价、分佣或利润结算。共创发起人只用公开昵称；平台自研注册、身份、编辑、权限和后台等 Foundation 归属不转给客户项目。

## 自动构建与审核

源代码 push 自动触发原 Site Hub CI，执行发现、回归、浏览器测试和候选打包。未审输出有送审预览标识，打包也标记 preview_only，生产发布器拒绝它。

内容审核由原独立链在 PR122 追加机器记录：首行为 `XUANJUN_SHOWCASE_REVIEW`，其后是 JSON，字段为 decision（PUBLIC_CONTENT_APPROVED 或 PUBLIC_CONTENT_REVOKED）、reviewer_role（INDEPENDENT_AUDITOR）、commit、ci_run_id 和 object_sha256 数组。审核应检查该批完整源码、资源、接口、权限、测试及声明，不由代码作者自签。

声明哈希采用排序键、UTF-8、不加空白的规范 JSON SHA256。CI 可生成该批对象清单。验证器回读真实 PR122 评论、发布主体、精确成功 CI、原始 Git blob 内容。新旧声明和评论缓存避免重复抓取。

安装到仓库默认分支的 Review Event workflow 只接受原 Owner 的 PR122 内容审核事件。它核对精确已通过的提交，并为该提交创建不可改写的 pr122-reviewed-* 标签，再从该固定版本调度原 workflow_dispatch 构建。开发分支继续前进不会迫使客户看到未审代码；既有标签指向不同提交时停止，不覆盖标签。标签不是新的任务分支或队列。事件工作流的 contents:write 仅用于这项固定标签操作，运行代码来自已安装到默认分支的受审工作流。首次安装前该事件通道并未生效；不得以分支上存在 YAML 声称已启用。首次激活或受控恢复时，执行方可以追加 XUANJUN_SHOWCASE_BUILD_REQUEST 及真实 review_comment_id，工作流回读原审核评论后构建；该请求不签发审核结论、不替代独立审核。

已审核构建使用历史真实内容审核记录自动发现所有获审版本。后续新增项目或角色只需开发、提交和内容审核，不需要 Work 手工改中央菜单。直接依赖新后台 API 的功能，必须先通过该后台的既有受控 Runtime 发布及兼容性验收；这个静态通道不把未经发布的 Python 代码自动运行到生产。

## 一次性国内接线

静态展示使用独立 `/var/lib/xuanjun-showcase` namespace 和 current，不覆盖原官网 current。只在原 apex HTTPS server 增加一个精确审过的 `/showcase/` include。不增加 DNS、限流 zone 或新业务后台，不重装旧隔离模拟服务。

安装器绑定新许可、完整机制 Manifest、精确 CI、主站 current、完整 Nginx 来源哈希及主进程身份。先保存旧 HTTPS 配置，写入有哈希记录的代码、配置和 timer，校验 systemd / Nginx，再接线。发生部分失败保留 receipt；禁止再次 install。回滚只处理其拥有且身份匹配的文件，恢复原 HTTPS include，保留所有站点和事务证据。

它需要一份已存在、root:root 0600 的 GitHub 只读凭据文件 `/etc/xuanjun-showcase/github-readonly-token`，用于读取 PR 评论和 Actions 制品。不能把凭据贴入聊天、仓库、命令历史或发布日志。当前未证明目标机已有该文件，仍是一次性准入前置。

展示路径禁用旧文件句柄缓存并使用 no-store，避免浏览器继续展示前一快照。新 timer 每五分钟读取获批发布事件，不使用模型；网络凭据只发给 api.github.com，不转发到制品存储重定向。它不会执行制品中的代码。过期许可不会被消费。存在未知事务、父版本漂移、哈希错误、下载/权限失败或缺少 HTTPS 回执时，保存 AUTOMATION_HOLD.json 并停止网络及发布重试；需原操作方核实、恢复并归档 HOLD 证据后才能继续。不会无限重试。

## 制品发布及恢复

生产候选只包含 `/showcase/` 命名空间内已审核的静态文件。源快照、每个公共文件、Manifest 和精确 GitHub Artifact 全部绑定。生产发布许可首行为 `XUANJUN_SHOWCASE_RELEASE`；独立制品复核首行为 `XUANJUN_SHOWCASE_PUBLICATION_REVIEW`。完整字段由 promotion.approval 验证，必须包含新单次许可、最长两小时有效期、同事务回滚许可、精确 CI/commit/artifact/hash 和父版本。

首次机制安装另需 `XUANJUN_SHOWCASE_INSTALL` 与 `XUANJUN_SHOWCASE_MECHANISM_REVIEW` 的精确授权/独立结论。所有字段在 install.gate 中校验。请集中审核整批机制和新增内容，继承未变已通过部分；代码作者不能代签这些结论。

发布器复用原已审静态发布引擎，唯一固定策略适配是新的 BASE；原源码 SHA256 保持 7253f3…93895。prepare、版本树密封、指针封套、锁、期限、check、reconcile、rollback 继续复用。已密封的旧版本、输入快照和回执保留为回滚制品；不会覆盖旧版本。

真实 HTTPS 验收逐文件核对公开响应、TLS 和安全头。成功状态为 HTTPS_SMOKE_PASS_AWAIT_BROWSER，不能代替生产桌面/手机视觉验收。浏览器、旧站导航、深层链接、语言及业务回归必须再实测。

部署顺序：新版官网静态候选先按其既有包装发布；随后一次性安装展示通道；再由新通道消费该批真实许可。父级失败恢复按“停止新通道 → 恢复展示快照 → 回滚通道接线 → 按旧包装回滚官网”处理。各步必须先核验自己的实际状态，不盲目串联重试。r1/r2 记录、备份、Tokyo 后台全部保留。

## 本轮证明边界

本地测试和 Hosted 测试可以证明数据选择、路由生成、多项目隔离、角色新增、版本回退、验收转案例、双币报价复用及静态发布恢复。安装测试的 systemd/Nginx 为显式假实现；Hosted 浏览器是 loopback，不是国内生产 HTTPS。

真实支付、真实购买、余额、佣金发放、客户身份/权限后台、未交付的多角色产品界面及新业务 Runtime 的自动升级，均不因本机制建立而宣称已完成。

本轮同时继承 PR122_CUSTOMER_CENTER_PRIVATE_MATERIALS_RULES_V1_20261016.md。公开展示目录和 visibility 标记不是私有资料权限系统；当前动态展示不得接收合同、身份证明、客户附件或密钥。客户中心及其14项真实验收另按同一 PR122 要求实现，不在本批公开展示测试中冒记 PASS。


## S1 修订：Owner 受保护独审锚（2026-10-16）

本节替代此前仅以 GitHub login 白名单和 reviewer_role 作为独审授权的说明。
GitHub 评论账户可以相同，但必须由 Owner 另行核实不同的源码作者与独立审核主体、保管证据，并在受保护执行机固定路径
`/etc/xuanjun-showcase/INDEPENDENT_REVIEW_TRUST.json` 登记准确审核锚。源码、评论、CLI、环境变量和仓库 policy.example 均不能注册此信任。
文件必须 root:root 0600、单硬链接，所有父目录 root 所有且不可被组或其他用户写入，不接受符号链接。代码不提供登记、签名或生成独审凭据的接口。

信任 schema=1，字段为 source_writer_principal、reviewers、revoked_review_ids、anchors。
reviewers 按独立主体索引，包含 status=ACTIVE 与 custody_evidence_sha256。
anchors 按真实评论 ID 的十进制字符串索引，每项固定 body_sha256、scope、reviewer_principal、custody_evidence_sha256、issued_unix、expires_unix。
锚有效期最多7天；主体不得等于源码作者；保管证据必须匹配 Owner 登记。scope 仅 CONTENT、PUBLICATION、MECHANISM 三种且不互通。
完整原始评论字节的哈希同时绑定评论中的对象哈希、源码版本、CI、模块上架范围或制品身份；已有准确源码/CI/对象成员检查继续执行。
评论修改、审核撤销、主体停用、身份混同、过期、范围变化或缺失登记全部拒绝，不回退到旧角色字符串校验。
该方案依赖 Owner 受保护锚的真实登记过程，不把角色自述当作独立身份，也不宣称生产保管证据已经取得。

原 issue_comment 工作流现在仅提供 HOLD 通知，权限为 contents/issues read；不创建标签、不调用 dispatch、不执行评论指定的源码。
正式构建仍需在获准的受保护构建通道读取固定信任文件，普通 Hosted preview 不需要该文件。
当前没有替用户登记真实信任，也没有部署受保护 builder，因此真实审核事件自动构建接线仍 HOLD。
这是关闭不安全旧入口的明确限制，不将通知工作流称为已经恢复自动正式发布。后续受保护 builder 的身份、独立凭据保管、只读信任装载与撤销同步须另绑定准确实现审核。
原 review-comment-id/reviewer 参数仍仅用于筛选评论，不能授权。最终制品独审、单次限时发布许可、备份、回滚和现场验收继续必需。
源码测试夹具的信任对象只供隔离测试，不复制到生产或当作真实审核。


## 受保护构建器候选增量（2026-10-16，尚未部署）

真实首批内容审核评论6214465866已回读：完整原始正文UTF-8 SHA256为
`156711523974f62e2f9df7753af9af3d1879c5f45678ace617b0ed2471aa181c`。
绑定内容提交80e77b7249dfa6ec73f1ffccb74200ec7eda4ad5、CI38892258900、9对象、无module商业上架。
此处记录真实评论身份，不产生生产信任。Owner仍须实际核实独审主体与保管证据，并在原固定信任文件登记CONTENT锚；不得把源码作者或本候选文档当作独审保管证明。

新增 `pr122_showcase_protected_build.py` 与 `xuanjun-showcase-build.service`，仅候选源码，无现场安装或执行许可。
执行代码固定为已安装 `/usr/local/lib/xuanjun-showcase`，由机制Manifest完整绑定且root保护；不得从内容提交执行Python、workflow、构建钩子或其他命令。
CLI无任意参数；固定国内主机/root检查。服务启动前先核验Owner私有请求中的准确机制Manifest哈希和脚本文件哈希，再导入固定代码；main再检查机制清单绑定的完整scripts执行依赖、路径、所有者、写权限、自身绑定及脚本文件size/SHA。旧安装器只复制scripts执行闭包；文档/静态数据/服务候选留在送审包，不错误要求它们全部存在于CODE目录。

请求固定路径 `/etc/xuanjun-showcase/BUILDER_REQUEST.json`，root所有0600单硬链接，祖先root不可组/其他写、无符号链接。schema=1，准确字段：commit、ci_run_id、review_comment_ids、reviewer_logins、mechanism_manifest_sha256、shell_tar_sha256、legacy_pages_sha256、issued_unix、expires_unix；一次请求有效期最多两小时。
它只选择待构建数据，不签发内容批准或发布许可；reviewer_logins本身不能授权。
当前首批commit/CI/comment分别为上述准确值、38892258900、[6214465866]。机制哈希必须取新增builder通过独审后的新机制制品，不能复用旧41文件清单。
外壳包固定 `/etc/xuanjun-showcase/APPROVED_SITE_SHELL.tar.gz`，root0600、完整TAR SHA绑定，由已审核的官网体验包提供；不接受测试占位外壳替代正式页面。

从GitHub只读API取得准确commit/tree与成功指定workflow CI后，只下载showcase/projects内声明/静态资源以及published-main-r2.json；拒绝链接模式、隐藏/穿越路径、Python等非公开资源、重复路径、截断树、Blob Git SHA错误和超限文件。
远端源码/工作流不会被执行。静态JS作为审核后的网页资源打包，不在builder执行。
固定受保护CONTENT锚验证后才进入原发现/选择/页面hash/模板/打包调用链。模块价格当前为空，未接权威库时不伪造商品或价格。
旧页面映射JSON另受请求SHA绑定；这只绑定候选所引用的基线，不声称生产旧URL再次浏览器验收通过。真实站点仍需发布前漂移检查及HTTPS回验。

输出只在预先经许可创建的root:root 0700 `/var/lib/xuanjun-showcase-builder` 下，按完整请求SHA生成唯一build目录；已有目录拒绝，不清理、不盲目重试。
生成pending候选后，重新读取请求/信任、检查有效期，再回读真实审核评论/CI并重新验证独审锚。最后检查信任未变、期限仍有效，写fsync回执、fsync候选并更名SHOWCASE_RELEASE.tar.gz、fsync目录。
失败保留BUILD_HOLD.json和输入，retry_allowed=false；没有调用原发布器、Nginx/systemctl、current切换或客户中心动作。
候选回执绑定源码/tree/CI、评论、请求摘要、信任快照摘要、机制摘要与最终TAR/Manifest哈希。回执及候选不是生产发布许可；后续发行前仍须重新审实际制品、核查撤销及取得新单次许可。

仍未实现/未执行的现场接线：
- Owner实际信任/请求/外壳注入、目录及代码安装；本增量不增加客户root通道动作，不通过inspect代装。
- 候选builder unit的国内隔离验收、实际启动及回滚归属；新service未加入旧install器自动安装范围，需准确一次性安装事务审查，不能声称旧install会装它。
- GitHub事件到受保护请求更新、固定root调用和正式候选上传Actions Artifact/CI绑定。当前通知workflow继续HOLD，不自动执行新builder。
- 正式实际SHOWCASE_RELEASE生成、制品独审与单次发布许可、真实域名浏览器和手机验收。

该增量完成“固定代码、数据分离、生成候选”的核心，并明确保留上述部署/自动接线门禁；不将核心代码完成夸大为整条自动更新系统已上线。模拟测试使用测试信任和网络夹具，不登记真实信任或生产批准。


## 完整生产接线候选：安装、事件、固定能力及上传（2026-10-16，未执行）

本节替代上个核心节点“安装器未扩展/事件尚未实现”的现状描述；此前已审核心和9项内容不重做。
源码现已提供以下完整调用链，实际安装/默认分支激活/Owner信任登记/国内验收仍未执行。

### 一次性安装及准确计划
原安装器增加只读plan，完整核对机制文件、现网Nginx/current/主进程、Runner UID1002、Owner私有输入、现有sudoers与新sudoers。输出plan及plan_sha256，不安装或改current。
原install要求新scope=STATIC_SHOWCASE_WITH_CANDIDATE_BUILDER、准确manifest源码commit、plan_sha256、单次/最多两小时/允许本事务回滚的独立许可；旧scope许可不能重用。
在原事务内增加builder unit、root0700输出目录、固定wrapper与精确sudoers；写文件后通过fchmod设置准确权限，不受umask077影响。激活前重验私有输入摘要、独审许可、Nginx/进程及期限。
只安装builder服务，不在安装过程中构建内容。原publisher timer与/showcase/ include仍按原许可流程处理；不改主站current、DNS、原隔离演示Runtime或客户中心。
回滚先核对所有权/哈希及旧配置，停用本事务服务，移除本事务wrapper/sudoers/unit、复核真实visudo并恢复原include。输出目录和证据保留，不删除Owner私有输入。失败/未知保留事务，不再次install。

### Owner私有输入（不得由作者伪造）
固定root配置目录下应由Owner通过私有方式准备：
- INDEPENDENT_REVIEW_TRUST.json：独审主体、真实保管证据、首批CONTENT评论6214465866及完整body SHA、获审新MECHANISM评论及准确全文摘要/范围/有效期/撤销状态。作者不代签或自动登记。
- github-readonly-token：仅仓库只读API/Actions读取，root0600。不贴GitHub、聊天或CI日志。
- APPROVED_SITE_SHELL.tar.gz：获审真实官网外壳包，root0600，不能用测试占位壳。
- BUILDER_POLICY.json：root0600，schema=1及准确mechanism_manifest_sha256、shell_tar_sha256、legacy_pages_sha256、reviewer_logins。私有政策不能由评论或workflow传入。
BUILDER_REQUEST.json必须在首次安装前不存在；以后只由固定channel从Owner已登记的真实内容评论派生。它不是额外人工维护每个页面的菜单或商品列表。

### 候选专用root能力
新独立wrapper /usr/local/libexec/xuanjun-showcase-build只允许inspect、build、export三种无额外参数动作；不修改原客户中心四动作通道。
bootstrap先验证Owner政策及已安装机制的脚本闭包，再导入固定代码。shebang只用单个-I参数，入口显式关闭pyc写入，避免Linux把多参数shebang当成一个无效选项。
build只使用Owner私有CONTENT锚，验证真实评论ID/正文/范围/独立主体/有效期，派生受保护请求并调用唯一builder unit。评论自身和事件都不能授予root或选定命令/路径。
按完整政策/信任/评论快照摘要去重，成功不再次构建；PREPARING/HOLD/未知状态先于网络检查拒绝重跑。失败/超时持久HOLD。
与安装/回滚共用既有外层事务锁，再持有内部build/export锁，避免撤回通道时又启动新构建。活动审核选择有数量和时间预算，不无穷扫描。
export只导出已完成构建的静态TAR与非秘密回执；再次核对信任/撤销/输出哈希，既不导出政策/Token/信任文件，也不执行发布。

### 实际内核证据及凭据保护
builder必须在实际服务中证明UID0但CapEff=0、NoNewPrivs=1、代码/配置挂载只读、输出挂载可写，并记录自己的mount namespace；channel要求它与调用者namespace不同。未达到则不封存/导出候选。
CI另外增加真实Hosted transient systemd sandbox probe；它不等于国内目标机验收。模拟单元测试明确使用合成runtime记录。
Github只读token从固定root0600文件读取，放Authorization头；API固定api.github.com仓库路径，不走环境代理、不跟随重定向，TLS客户端不启用环境keylog，错误对外清洗。此实现不冒称客户中心Telegram R3目标机已验收。

### 事件到正式候选上传
原issue_comment工作流默认不运行；仅Owner设置PR122_SHOWCASE_PIPELINE_ENABLED=true并配置PR122_SHOWCASE_BUILDER_REF后才调度候选构建。ref必须为pr122-showcase-builder-加40位获审源码SHA的固定tag；事件不创建或覆盖tag，不合并源码，不签发root许可。
调度原pr122-site-hub-preflight.yml的protected_builder=true分支。该job只在获准tag、Owner启用开关下使用国内既有Runner，校验实际host/UID1002；没有checkout/执行远端源码步骤。
调用固定root build/export后，在普通Runner临时目录解码静态TAR并核对SHA；回执内mechanism_source_commit必须等于workflow GITHUB_SHA。然后上传TAR、BUILD_RECEIPT和CI_BINDING到Actions Artifact；源码CI/内容CI/制品CI分别记录，不混同。
原workflow ID保持不变，兼容原发行器的准确CI/Artifact门禁。数据内容提交可继续前进，执行代码仍冻结为获审tag。新功能页面只需原目录登记、内容审核与Owner受保护准入，不需要Work改中央菜单。
审核评论在Owner登记之前到达只会WAIT，不产生root请求；登记后可在原PR122发BUILD_REQUEST作为恢复触发，仍不代替内容批准。

### 部署顺序及仍需的实际许可
先按既有体验事务发布获审首页/导航/商家UI；再针对更新后实际站点生成本机制的新plan并取得准确安装许可，避免旧UI包装的Nginx基线与新include互相冲突。
Owner完成私有登记后，按准确plan单次安装新机制；验证实际unit/sudoers/Runner固定调用及隔离。由既有受保护GitHub通道将两份准确workflow激活到default并固定获审tag及两项Owner变量，不绕过分支保护、不合无关Stage5历史、不另建业务任务。
然后运行一次真实候选构建/上传；对实际TAR/ZIP/Manifest/Root运行证据集中独审，再签新单次SHOWCASE发行许可，执行HTTPS/手机/旧导航与回滚验收。
尚未取得新的安装或发布许可；没有执行上述生产步骤。现网、客户资料接入及客户中心准备门禁保持原状。若私有主体/保管证据或真实凭据缺失，保留具体缺项，不伪造配置或要求客户把秘密贴到聊天。
