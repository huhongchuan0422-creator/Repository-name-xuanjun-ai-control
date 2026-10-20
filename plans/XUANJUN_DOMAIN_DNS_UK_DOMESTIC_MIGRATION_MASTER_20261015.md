# 玄钧云汇自有域名、DNS、官网迁移与可视化交付权威规划 V1.0
**日期：2026-10-15｜工作锚点：Stage5 Issue #76、Draft PR #122｜原审核冻结基线：PR #118 HEAD `71024b22f0d6110f0507dbd8476468313f8846f2`**

> 当前执行状态以第9节最新编号记录为准。旧节中的“DNS未切换”和历史UNKNOWN仅描述当时状态：主域实际切换已由独审6206608746验收通过，不得据旧表重复操作DNS或重做已通过检查。

## 0. 权威结论与证据等级

**业务决策（OWNER_CONFIRMED）**
1. 东京服务器即将到期并计划撤销；不再将东京作为官网、客户预览、CRM或新模块的长期依赖。迁出+验收前不可先停机。
2. 以**国内服务器负责中国客户的官网/SaaS可视化/社区分账预览**、**英国服务器负责代码控制、开发调度、审计、受控部署及管理**为目标架构；韩国服务器保留原业务隔离。
3. 所有客户预览须使用自有域名的HTTPS网页，不要求ChatGPT登录；客户公开案例与客户私有预览分开；客户AI、Telegram、飞书统一身份与可审计反馈。
4. 必须先查证官网当前入口/源站/内容目录，再生成可执行部署计划；DNS切换、生产发布、东京撤销都必须单独通过发布授权、备份和回滚门禁。

**证据分级**
- `E1_USER_SCREENSHOT`：用户于2026-10-15提供Cloudflare DNS控制台截图，展示12/200条记录。证明截图时的配置，**不等于此刻全球权威DNS或实际网站服务器验证**。截图域名栏/部分行名被UI截断，完整主机名须在Cloudflare导出或DNS API读回后确认。
- `E2_CONTAINER_NETWORK_PROBE`：本次工具容器中`socket.getaddrinfo`对主域、uk、winctl、center等均报 `Temporary failure in name resolution`；curl访问主域报6、访问47.101.152.210和47.245.53.152:443报7。只能证明**当前工具容器网络不可用**，不能据此判断官网实际宕机。
- `E3_PUBLIC_WEB_FETCH`：公共网页工具访问主域报不可访问，center报DisabledError；没有取得HTTP响应页、证书、server header或源站证明。
- `E4_GITHUB_CODE`：Draft PR122有`demos/visual/community-payment/index.html`及`demos/community-local-e2e/**`可视化资源，**仅表示已提交代码**；仓库`.github/workflows/v27-four-server-batch-readonly.yml`及`scripts/v27-batch-readonly.sh`表明既有四机只读探针意图，不能证明该Runner目前在线/有权限/可读网站配置。
- `UNKNOWN_SITE_OWNER`：尚无真实Nginx/OpenResty/Apache配置、root/upstream、systemd、部署回执、目标主机SSH/Runner输出。因此“官网实际运行在哪台服务器”**暂不能最终确认**。Cloudflare A解析指向东京IP不能证明网页静态文件或动态服务全在东京，也可能再反代英国/国内。

## 1. Cloudflare现有DNS基线：逐记录登记（勿覆盖）

用户截图为 `wenwenwenyiyiyi.work` Cloudflare DNS 记录表，12条，代理均显示“仅DNS（DNS only）”，TTL自动。截图视觉可识别如下：

| 序号 | Host（截图可识别/待精确读回） | RRtype | 内容 | 代理 | 规划动作 | 判断 |
|---|---|---|---|---|---|---|
|1|`uk.wenwenwenyiyiyi.work`（截图显示uk前缀）|A|`8.208.119.115`|仅DNS|先保留|英国服务器入口线索；主机服务仍待核查|
|2|`wecom.wenwenwenyiyiyi.work`（截图显示wecom前缀）|A|`47.245.53.152`|仅DNS|迁移清单中列为东京依赖，**先核后迁**|不能因名称判断真实企微能力|
|3|主域 `wenwenwenyiyiyi.work`（截图显示截断）|A|`47.245.53.152`|仅DNS|国内站验证通过后，拟由东京切至国内，**尚未执行**|指向东京出口IP的DNS线索，非网站root证明|
|4|`winctl.wenwenwenyiyiyi.work`（截图显示winctl前缀）|A|`47.101.152.210`|仅DNS|保留并核对国内运行用途|此IP是现有国内服务器线索|
|5|`center.wenwenwenyiyiyi.work`|CNAME|`custom-domains.chatgpt.site`|仅DNS|**保持原样**|不是英国服务器A记录；ChatGPT自定义域名入口不能当作英国Nginx部署入口|
|6|主域MX（优先级54图标数字；请导出核对）|MX|`route3.mx.cloudflare.net`|仅DNS|**保留**|Cloudflare邮件路由，不得误改|
|7|主域MX（优先级11图标数字；待核）|MX|`route2.mx.cloudflare.net`|仅DNS|**保留**|同上|
|8|主域MX（优先级85图标数字；待核）|MX|`route1.mx.cloudflare.net`|仅DNS|**保留**|同上|
|9|`cf2024-1._domain...`（UI截断）|TXT|DKIM公钥文本（UI截断）|仅DNS|**原样保留**|邮件签名|
|10|`_cf-custom-hostna...`（UI截断）|TXT|Cloudflare自定义主机名验证文本（UI截断）|仅DNS|**原样保留**|证书/域名绑定校验，勿删|
|11|`_openai-site-verifi...`（UI截断）|TXT|OpenAI网站验证文本（UI截断）|仅DNS|**原样保留**|现有自定义域名所有权验证|
|12|主域TXT（UI截断）|TXT|`v=spf1 include:_spf.mx.cloudflare.net ~all`（截图）|仅DNS|**原样保留**|邮件SPF|

**重要：** 截图上的MX右侧54/11/85位于“详细信息”图标附近，**不能直接断言是MX优先级**，上表仅保留截图视觉读数作为待核实记录；以DNS导出中的`priority`为准。所有UI截断字段须实际读回完整值。**此阶段DNS写入=NO、TTL/代理模式更改=NO**。

## 2. 统一主域与子域 / URL 信息架构

| 外部入口 | 用户/用途 | 目标承载层 | URL/路由性质 | 当前状态 |
|---|---|---|---|---|
|`https://wenwenwenyiyiyi.work/`|官网公众入口|国内公网入口 + 必要的安全反代|既有域名，源站待核|DNS截图A指东京；实际服务UNKNOWN|
|`https://wenwenwenyiyiyi.work/visual/`|统一可视化中心，行业/项目/模块案例|国内站静态前端+可信应用API|规划路径，按既有路由协调|NOT_DEPLOYED|
|`https://wenwenwenyiyiyi.work/visual/community-payment/`|社区分账多角色公开演示|国内站隔离DEMO|已有GitHub资源路径映射候选|NOT_DEPLOYED|
|`https://wenwenwenyiyiyi.work/marketplace/`|SaaS模块目录/价格/选购|国内官网或既有SaaS入口|**仅候选**；先查现有路由避免重建|ROUTE_PENDING_REUSE|
|`https://wenwenwenyiyiyi.work/customer/projects/<project>/preview/`|定制客户演示+反馈+验收|国内站可信身份/授权API|私有路由，正式登录/权限隔离|AUTH_PENDING|
|`https://uk.wenwenwenyiyiyi.work/`|英国主机指向/内部开发支持|英国|**已有A域名，服务未知**|DNS_ONLY_EVIDENCE|
|`https://center.wenwenwenyiyiyi.work/`|用户现有管理中心/ChatGPT自定义域|现有ChatGPT域名服务|现有CNAME；不改DNS、不用作网站发版|KEEP|
|`https://winctl.wenwenwenyiyiyi.work/`|国内现有子域|国内IP|现有A；业务/权限待确认|KEEP_PENDING_AUDIT|
|`https://wecom.wenwenwenyiyiyi.work/`|原企微相关入口|当前指向东京|需专项迁移与Webhook验证|MIGRATION_HOLD|

**不新增解析记录即可规划同一个根域的多个PATH**；同根域 `/visual` 等不是DNS记录，是否能访问取决于站点路由及发布。禁止创建与既有官网深层多语言导航冲突的`/zh-cn`、`/en`及/visual变体；应先做URI清单和语言回退策略。所有客户预览必须在自有域名HTTPS、普通浏览器无需ChatGPT帐号。

## 3. 业务与服务器职责 / 东京退役门禁

| 节点 | 目标职责 | 禁止事项 |
|---|---|---|
|国内 `47.101.152.210`|官网、SaaS可视化中心、公开案例、已认证客户项目预览、反馈表单/AI前端；复用既有CRM/客服|不得未经审核写入生产站、混淆DEMO与付款|
|英国 `8.208.119.115`|开发/测试/版本审计、GitHub受控Runner、制品签名/发布编排、任务进度；必要时经过安全评估反代API|不得把`center`的ChatGPT CNAME误写成英国A；不可绕过PR17 P2门禁|
|东京 `47.245.53.152`|迁出前保留旧官网及`wecom`等现有运行路径直至新链路证明一致|撤机前不可移除DNS、回调、证书或回滚资产|
|韩国|继续既有业务隔离|不因国内/英国迁移借用韩国端的受限业务环境|

**国内客服飞书边界（Owner 于 2026-10-20 明确）：** 国内客服入口固定复用已有 `XuanjunAICustomerService`（App ID `cli_aa4dc861c0385cbd`），任务服务器为国内 `iZvt5t8tlrm8oiZ`（`47.101.152.210`）；用途是替代企业微信承接客户咨询，复用统一 CRM 与网页 AI。身份定义及历史接续要求统一引用开发主文档第8.2.7节，覆盖第8.2.3–8.2.8节相关入口，不在本计划另建权威状态。先只读核实已有应用、配置、租户/回调、客户绑定及历史，再续接原资产；生产接线与历史兼容结果未核实均为 `UNKNOWN`。

韩国币安飞书、开发控制飞书、认证通知飞书保持独立，禁止混淆或借用应用/凭据/回调/历史；英国开发控制职责不等于国内客服承载。替代企微是任务目标，不是已完成切换或删除旧 `wecom`/企微回调的授权；东京迁出、DNS、生产发布与旧依赖处置继续按原门禁单独验收。

**东京下线必要条件（全部证据齐全）**：官网主/深层路径、语言导航、静态资源、微信企微回调、Telegram、网站客服、客户预览、定制资料、证书、任务/定时器、备份、DNS切换后的24h以上真实请求观察（时长需Owner确认）及紧急回滚均PASS；交易/其他租户项目另行验证完成。未列出的站点依赖采用UNKNOWN并明确阻塞，不推断为0。

## 4. 官网源站定位：可执行的只读核查步骤（UK/Domestic优先、Tokyo仅原站快照）

1. **DNS事实**：在Cloudflare以只读导出方式取得完整12条记录：`name,type,content,proxied,ttl,priority,comment`及时间；从国内和英国实际Server Runner用`getent ahostsv4`、`dig +short A/CNAME`核对。不得更改Cloudflare。
2. **站点接入**：在国内、英国、东京三台机器**只读**运行 `hostname -s; ip -4 address; ss -lntp | grep -E ':(80|443) '; systemctl list-units --type=service ...`，记录服务名和端口，不读取或传播私钥。
3. **HTTP Host/源站**：分别在主站候选IP上用经授权的`curl -kI --resolve wenwenwenyiyiyi.work:443:<IP> https://wenwenwenyiyiyi.work/`测试响应状态、重定向、证书主体、URL、响应标头，并与公网真实请求响应匹配；`-k`只用于证书诊断，最终验收必须无`-k`通过有效TLS。
4. **Webroot/代理**：只读 `nginx -T`时过滤可能含凭据的location/环境变量；核实server_name、root/alias、proxy_pass、静态路径及既有语言路由；必要时用文件哈希/同一可公开校验标记对比各主机与公网，确认事实源。禁止暴露完整配置和密钥于工单。
5. **既有发布通道**：列出实际GitHub Runner/服务身份、发布PR、systemd/容器、回滚快照及权限，以`PR17/P2_RELEASE_GRANTED`保持现有值；没有权威门禁就不发版。
6. **结论格式**：`APEX_DNS_IP`、`PUBLIC_HTTP_ENDPOINT`、`WEBROOT_OWNER_HOST`、`UPSTREAM_SERVICE_HOST`、`TLS_TERMINATION_HOST`、`DEPLOY_AUTHORITY`各自给出PASS/UNKNOWN和证据；不把DNS指向当成webroot证明。

已有workflow `.github/workflows/v27-four-server-batch-readonly.yml`是**已发现的复用资产**。当前`tools.mcp__GitHub__`没有提供`workflow_dispatch`触发动作，故本轮**未运行服务器探针**；不得伪称已经完成四机核查。

## 5. 自有域名分阶段迁移/发布方案（待Release Gate）

- **D0只读发现**：完整DNS/证书/站点源站、东京服务与回调、国内容量、备案及当前网站变更冻结，输出清单。
- **D1无公网改动**：在国内隔离目录准备正式官网+静态DEMO制品，绑定准确commit、manifest、SHA256，验证相对路径 `demos/visual/community-payment/..` 与 `demos/community-local-e2e/**` 的引用不失效；不可直接以当前GitHub文件覆盖生产文件。
- **D2国内预检**：用Host override/测试监听端口逐项验证首页、`/zh-cn`、`/en`及原98深层URL、`/visual`、全部多角色入口、输入交互、反馈禁用安全标记、403/404、跨租户负向及非ChatGPT浏览器；有权威SSL证书、日志和回滚资产。
- **D3正式审批发布**：独立源码+制品审查、英国控制面机器回执、Owner放行；通过后原子切换国内Web root/路由。内容上线与后端身份/真实客户反馈的Release Gate相互独立，不得把静态演示标为生产客服。
- **D4 DNS切换**：只有D2/D3及回滚均验收后才将根域A目标改为国内适用入口IP或采用已经批准的等价路由；做前后DNS快照及TTL/全球传播观察；不动MX/TXT/center。
- **D5外网验收**：普通PC/手机、不同网络地区实测HTTPS200、导航、模块组合、多角色及申请审核；客户网页AI/Telegram/飞书身份和消息账本按实际连接状态单独验收。
- **D6东京退役**：逐个解除旧域/服务依赖并验证无请求与资产保留，最后单独准许停机和释放。东京资源到期前若无法过门禁，须Owner决定延期或受控业务降级，不能“默认自动撤机”。

## 6. Work/Dots协作与证据归属

统一发布锚点：**GitHub PR122 与此文档**；冻结审计基线 PR118 不改。Work为独立审核/受控Web与主机操作执行者（其Cloud Browser/计算机操作须在Work模式实际启动），Dots可用于协作跟进；两者先读这份文件与PR122最新回执，避免创建第二套站点/域名方案。本轮**没有直接发送到Work或Dots聊天的原生工具**，因此Github共享回执是唯一已实际写入的协调载体；`SYNC_WORK=IN_GITHUB_HANDOFF_ONLY`、`SYNC_DOTS=IN_GITHUB_HANDOFF_ONLY`，不宣称对方已消费消息。

## 7. 未关闭事项及终态

`WEBSITE_ACTUAL_HOST=UNKNOWN`
`CLOUDFLARE_LIVE_EXPORT=NOT_READ`
`UK_DOMESTIC_HOST_PREFLIGHT=NOT_RUN`
`FIRST_PARTY_CUSTOMER_PREVIEW_GATE=HOLD`
`OMNICHANNEL_FEEDBACK_IDENTITY_EVIDENCE_GATE=HOLD`
`DNS_MUTATION=NO`
`WEBSITE_PRODUCTION_DEPLOYMENT=NO`
`TOKYO_RETIREMENT=HOLD`
`PR118_FROZEN=YES`
`PR122_DRAFT=YES`
`PR17_P2_RELEASE_GATE=UNCHANGED`

## 8 跨PR共享依赖约束（2026-10-15）

执行时必须同时读取`plans/PR99_PR122_SHARED_DEPENDENCY_LEDGER_20261015.md`。PR99只负责东京币安最小生产运行时迁入韩国；PR122只负责官网及被实际证明为必要的网站依赖迁入国内；UK仅作为开发和受控发布控制面。两条线可分别准备和验收，但任何共享服务停止、数据库权威切换、凭据撤销、网络或DNS变化必须先证明不破坏另一条线。PR99或PR122任一PASS均不等于东京可退役；东京退役继续需要独立最终批准。


## 9. 2026-10-15 23:44 Asia/Shanghai：网站与服务器迁移执行节点（当前执行版）

**本节覆盖上文历史 UNKNOWN/待采集状态和23:35共享账本中“先开发完整OAuth迁移”的执行顺序；历史证据保留。** 两条迁移分别验收，不再将新后台开发混入网站切站。沿用PR122/PR99、原分支、制品与回执，不建立新任务队列。

### 9.1 已确认事实与范围冻结

- 东京官网真实源站已确认；国内已具备原Work V2静态候选。1187文件、11090700字节、current指针、canary ROLLED_BACK、stage CHECKED及8项本地HTTP验收已取得Owner终端证据，不重复做RG1。
- 最新国内Owner终端：DOMESTIC_APEX_CONFIG=False、DOMESTIC_APEX_CERT=False；直连47.245.53.152并以wenwenwenyiyiyi.work校验TLS成功，HEAD /返回200。该证据只证明根路径HTTPS可达，不证明所有动态请求、安全限制或回滚通过。
- DNS12条已补齐，Owner无需重新导出。切换时只复核将改记录的当前值，不重新要求整套资料。
- OAuth候选d584cd60b31bf09ee45f27a73ad227bcd0e1110f及Artifact11985605874已获源码限定通过、完整制品PASS与push45/45。保留为后续服务器迁移资产，**本次最小网站切换不安装该候选，不迁其凭据，不重打包/重跑45项**。
- 最小网站目标：国内静态内容 + 必要动态请求暂保留东京原后台。临时HTTPS反代目前仍是待完成/独立审核的候选；单次TLS200不是生产批准。它不等于服务器全部迁移或东京可退役。
- 未提交迁移辅助草稿不纳入发布制品、不成为新的执行前置；不继续扩展新模块。
- 当前会话具备GitHub读写和CI证据通道，没有直连admin/root或DNS写入通道。githubrunner非root测试成功不证明拥有生产安装权限；不新增通用sudo/SSH密钥作为捷径。
- 下述计划本身不是合并、生产部署或停机授权；原独立审核和发布门禁继续执行。OpenClaw保持停止，PR99/PR17/P2不因本计划改变。

### 9.2 网站迁移：W01—W10

| 节点 | 当前状态 | 具体交付/动作 | 执行负责 | 完成标准与依赖 |
|---|---|---|---|---|
| W01 固定现有网站制品 | 已完成，沿用 | 复用原源归档、批准delta、最终Manifest、恢复回执 | 我复用GitHub/已有回执；不交Owner重做 | 源归档74545480...f66e63、内容Manifest eb2fcc07...c52f7及原批准内容保持绑定；不拿后续共享branch HEAD替代批准制品 |
| W02 国内静态隔离验收 | 已完成，沿用 | 复用已落地stage及1187文件/11090700字节、本地8/8证据 | 已有Owner执行；我引用结果 | current指向pr122-d8b08ed-recovery-stage；这是隔离验收，不是公网切换；尚未证明的完整路由在W06验收 |
| W03 必需路由接续清单 | 待完成，下一节点 | 基于已收集东京配置列全静态别名及所有动态location，给出国内静态/暂留东京对应关系；只补缺少的安全配置证据 | 我查GitHub/已上传源与已有配置；若确缺主机限定信息，由我出一次合并采集命令 | /p/、各/submit、OAuth start/callback/status/disconnect、health、Telegram webhook/status均明确接续；无漏路由、无把503当迁移成功 |
| W04 最小Nginx/反代候选及审核 | 待完成 | 复用现有模板，只补国内apex server、东京HTTPS上游和精确路由；集中测试、打包、独立审核 | 我负责代码/配置/CI/制品与送审；独立审核窗口签结论 | 上游固定IP+正确SNI+证书校验，避免DNS回环；保留认证/访问限制/Origin/方法/请求体语义；不记录secret/query/body；敏感POST超时不自动重试，未知结果不报成功；winctl隔离；有配置/指针/DNS回滚方案 |
| W05 国内apex证书与续期 | 未执行；当前证书不存在 | 使用已存在Certbot5.8.0与审过的脚本；按选定ACME路径完成国内challenge入口、东京仅challenge转发、证书签发及续期配置 | 我完成所有GitHub配置和命令准备；有已批准root通道则我执行，否则Owner执行一整段已审核命令 | 不提前改DNS；SAN正确、链有效、私钥留本机；续期dry-run及nginx-t后reload钩子验证；不覆盖winctl/IP证书；依赖W04及相应ACME变更审查 |
| W06 切DNS前整站验收 | 未执行 | 国内候选HTTPS以Host/resolve指定源站验证原109路由责任清单、资源、语言/别名、CSP及必需动态行为，保存日志 | 我提供/运行可用通道中的自动化检查；需root部分合并交Owner一次执行 | 不使用-k冒充TLS通过；原路径不缺失，访问限制不放宽；危险OAuth/支付/消息写入不得用真实业务试错；未获授权的真实动作另设门禁；配置/服务/回滚有绑定回执 |
| W07 网站切换放行 | 未通过 | 集中提交W03—W06准确版本、配置、证书、路由、回滚及现场回执 | 我整理完整证据；独立审核/发布门禁给出范围结论 | 网站切换范围明确通过；不把OAuth源码审核当Nginx上线批准；不把此节点作为东京停机批准 |
| W08 主域DNS切换 | 未执行 | 仅改已批准apex记录；先核其现值及可能影响同主机名的AAAA/代理模式，记录原值与回退步骤 | 有授权DNS连接由我操作；当前没有，则Owner仅执行控制台变更 | W07通过；目标47.101.152.210；不改center/wecom/winctl、MX/TXT/邮件记录；不删除未判明记录；读回确认 |
| W09 公网验证与观察 | 未执行 | PC/手机及不同网络检查首页/语言/深链/资源/动态请求、证书、错误日志及winctl；按批准观察窗口留旧站 | 我执行可自动化请求与证据汇总；普通终端人工体验确需时才请Owner | 实际公网命中国内、内容一致、关键路径保持、无新增安全退化；失败按批准方案回退，不盲重发写操作；观察时长在W07发布方案中明确 |
| W10 网站迁移关闭 | 未完成 | 记录新入口/版本/证书续期/配置/回滚位置/剩余东京依赖 | 我更新原计划、账本及PR122 | W01—W09验收齐全才报网站迁移完成；若动态后端仍在东京，明确“网站入口迁移完成，后台仍依赖东京”，服务器迁移继续进行 |

**网站顺序：** W01/W02沿用 → W03 → W04 → W05 → W06 → W07 → W08 → W09 → W10。W03/W04的GitHub工作不依赖Owner再次提供已给出的DNS、源归档或45项测试。

### 9.3 服务器迁移：S01—S12（以消除东京全部必要依赖为完成目标）

| 节点 | 当前状态 | 具体交付/动作 | 执行负责 | 完成标准与依赖 |
|---|---|---|---|---|
| S01 冻结东京依赖清单 | 部分完成 | 复用共享依赖账本和已收源码、单位/端口证据，补每项“迁往何处/谁仍调用/谁有写权” | 我完成仓库与已有证据整理；缺少的现场项集中采集 | 覆盖18080、CRM/DB、模型桥、Telegram、WeCom、Novel、交易/Finance、timer、证书、Runner和其他实际消费者；未知项不当不存在 |
| S02 目标归属和执行通道 | 部分完成 | 国内接运营/网站相关，英国接开发控制，韩国交易按PR99；绑定各自身份、路径、准许命令和制品 | 我准备配置与作用域；现场授权通道确实缺失才需Owner接入/执行 | 已有国内18443桥及东京19443入口原样保留直至替代验收；不因Runner可测试而推断root可发布；不启动P2/OpenClaw |
| S03 一致备份和恢复基线 | 未完成全量验收 | 逐服务做版本/配置/状态/DB及必要游标的受保护一致快照，规定静止/排空与恢复方法 | 我复用既有备份/回滚工具并测试；实际私有快照经受控主机通道 | 可恢复、权限正确、源/目标版本绑定，备份不进入GitHub/聊天；不能整目录含密钥随意打包；PR99交易快照遵其独立规则 |
| S04 最小运行时就绪 | 部分基础已有 | 复用国内现有runtime，不复制整套东京交易工程；补所需依赖、unit/config及启动顺序、独立路径 | 我完成源/依赖/配置/离线测试；主机安装按审核包执行 | 使用最小服务身份；无默认交易DB/主密钥耦合；端口/owner/mode明确；目标隔离启动、停机和重启可验证 |
| S05 运营数据及SecretRef接续 | 未执行迁移 | 仅按服务迁移其CRM/会话/去重/必要凭据，处理旧格式兼容、账号绑定、回调在途状态和单一写入权 | 我写最小必要适配及测试；真实秘密只走受保护主机通道 | 新旧账号/Token一致，失败不破坏旧绑定；无数据丢失/重复权威/秘密泄漏；既有OAuth审核资产复用，只有必要变更集中增量审核 |
| S06 混合Portal18080去依赖 | 未完成 | 按已有端点职责分离交易侧与运营侧；网站临时反代只在此节点后逐项替换 | 我负责必要代码/配置/测试/制品，主机部署按门禁 | /p/、提交、OAuth、状态、disconnect、健康等每个现有调用有已验收后继；旧会话/认证兼容可核对；旧服务不能提前停止 |
| S07 模型桥接与执行器去东京依赖 | 部分身份/health证据已有 | 复用现有桥，确认19443实际隧道目标及最终执行器归属，准备只需变更的配置 | 我完成已有代码核对与测试；隧道/运行态变更经受控通道 | 受限RPC、证书/HMAC、超时、无泄密、模型/responseModel/fallback及无害推理按授权验收；health200不替代推理PASS |
| S08 Telegram/WeCom/Novel逐服务接续 | 未完成 | 复用各自原适配器、认证和去重逻辑，逐个迁edge/callback及必要数据，更新对应入口 | 我准备配置/回归/回滚；实际provider变更及真实canary必须在各自授权范围 | webhook签名/secret、客户身份、去重、在途和未知结果、真实回调及回滚通过；不得为验证擅发客户消息；Novel及PostgreSQL/Redis无附带停机 |
| S09 交易与Finance迁移 | 独立PR99；本计划不重开 | 以PR99最新独立回执为准处理韩国runtime、交易DB、4个Finance/Billing timer、Writer/fence/epoch | PR99既有开发/审核/现场执行者；我只同步依赖结果 | PR99生产门禁通过且东京不再有权威DB/Writer/必要timer；PR122不复制trading.db、不停Finance、不绕过PR99 |
| S10 定时任务/证书/控制工作迁出 | 未完成 | 逐项移交剩余timer、renewal、备份、告警、日志保留、GitHub Runner和东京开发职责 | 我查已有配置并复用目标英国/国内通道，主机动作按限定包 | 每项仅一个有效调度/写入者、运行回执及失败告警可查；英国开发闭环P2/P3若另有门禁继续独立，不因本计划擅启 |
| S11 整体去依赖验收 | 未执行 | 对所有目标服务做业务链路、重启恢复、权限、数据对账和回滚；核查全部DNS/callback/tunnel/任务不再需要东京 | 我集中整理/自动验证；真实行为按批准范围 | 证据证明必要调用和写入权均已迁出；残留连接/任务/数据/未知依赖逐项关闭；观察窗口和受控旧服务隔离有审核回执 |
| S12 东京退役 | HOLD | 完成最终备份与账务/资产核对，获得独立最终退役范围及Owner批准后停旧服务、停机，最后释放资源 | 我准备可复核清单；获授权且有执行通道后执行，云控制台缺通道才请Owner | S01—S11及W10满足其范围；停机与不可逆释放分开，保留批准回滚资产；任何未解依赖阻断释放；只有此后报服务器迁移完成 |

**服务器顺序：** S01/S02 → S03 → S04/S05 → S06/S07/S08/S09按各自既有任务推进 → S10 → S11 → S12。它不阻塞W03—W10采用已审核的临时动态后端接续；反过来网站切换也不代表这些节点通过。

### 9.4 执行与汇报规则

1. 我负责能通过GitHub完成的源码/配置复用核对、最小补丁、测试、CI读回、制品/哈希、审核材料和账本更新，不把这些交给Owner手工做。
2. GitHub托管CI、非root实机测试、root部署、DNS控制台和生产验收分别记录；不得互相代替。当前无可用通道的root/DNS步骤列清楚，仅那部分交Owner执行合并命令/控制台动作，不让Owner反复查资料。
3. 先复用已完成证据；仅对新变更、已失败或缺证据的路径测试。独立审核仍由原审核窗口负责，开发方不自批；未变模块不重复审核。
4. 每个节点只有在“交付物+测试终态+审核范围+现场回执（若需要）”齐全时关闭；只写计划/提交代码不算完成。失败/超时/缺回执明确FAIL/UNKNOWN，不盲重试。
5. 不再将新增OAuth架构、社区新功能或P2/P3整体开发作为最小网站切换前置；最小反代方案必须保留已有安全边界并经W04/W07审核。
6. 下一活动节点固定为 **W03 必需路由接续清单**；W01/W02不重做，服务器S01只整理既有材料，不先启动新服务或迁移真实凭据。



### 9.5 W03交付及W04配置候选（GitHub自主执行记录）

东京既有Runner只读采集已完成：run38764344743/job116523523247，
commit6e747401b170fbd8179ca93e69c16529d73e853a，Artifact11987296370。
英国/国内/韩国job在本次push均SKIPPED，未碰P2或生产安装。
由githubrunner直接读取公共Nginx配置，未调用sudo/nginx-T或读取私钥；
敏感请求头、认证值及Telegram路径信息脱敏。新增采集回归10/10本地PASS，
该提交既有Hosted检查已通过；这是配置源码证据，不冒充重新加载后的生产状态。

W03路由清单已形成：75个location=62静态+11动态+1ACME+1默认404。
75是Nginx规则数，不是历史109个验收URL；109 URL仍由W06现场验收。
已生成逐规则责任表及当前Tokyo配置文件哈希，来源在minimal-cutover目录。
W03的清单交付完成；实际路由接续及安全等价性仍需W04独立审核/W06验收。

W04新增的是现有静态发布目录之外的最小Nginx候选，不改原RG1包或其Manifest：
固定TokyoIP、正确Host/SNI、系统CA验证、保留原方法/路径/query/body/认证头，
禁止上游自动重试/缓存/临时响应文件；静态CSP只作用静态location，保留动态
Portal自己的安全头。原两条submit精确路由保持，未开放整个submit前缀。
Telegram继续由Tokyo原Nginx嵌套控制和旧服务处理，不复制Bot Secret。

必须明确的未过门禁：系统CA路径需现场证明、国内apex证书/续期未配置；
Tokyo看到的网络对端将变为国内，因此原始客户端IP语义尚未证明等价，不能
宣称所有认证/限流/审计与生产业务不受影响。隐私保护下原始请求错误日志
被抑制，状态监控与排障策略也需审核。存在未展开的原Telegram嵌套控制，
保留在Tokyo原位置；禁止仅凭模拟后端测试就声称真实Webhook已通过。

新集成测试使用真实临时Nginx+本地假TLS上游，覆盖62静态别名样本、11动态
路由、TLS/SNI拒绝、方法/正文/认证和Telegram头透传、动态CSP不被静态CSP
覆盖、无秘密日志、敏感POST超时不重试。不是实机109URL/真实Provider验收。
本地无Nginx，真实Nginx测试不能记PASS；Hosted CI明确安装Nginx且缺依赖时报错。
新候选与完整测试/配置/来源单独打包送一次独立审核；不安装新OAuth，不迁凭据。
未变OAuth七模块+测试源精确哈希一致时复用源码/制品审核，不再重跑45项；
因采集器变更只运行其2项旧边界回归及新增采集测试。

当前节点：W03清单交付完成；W04配置/测试候选待准确提交CI与独立审核。
W05—W10未执行。生产、DNS/TLS切换、东京退役继续HOLD。


### 9.6 W04候选实测与W05只读前置补齐

W04初始准确候选ce76432a7050cfd0bd3410a1967624f969a253d9已取得push
run38765623755/job116527936823：81/81（含真实临时Nginx集成5项）及原采集
边界2/2通过。45项OAuth测试日志明确NOT_RERUN并复用准确源码/制品审核。
旧候选Artifact11989340547原始ZIP/内层/16文件绑定/8配置清单已由开发方
下载复算；这不是独立审核批准。下面CA绑定后的最终候选仍需准确CI和统一审核。

W05只读前置由我通过国内既有Runner完成，无需Owner拿资料：
run38765986129/job116529173285 SUCCESS，执行身份githubrunner。
系统CA=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem，root0444，148证书，
SHA256=acd28b791f9f338d288efda11d7f192755d4e89f41f0f7c2999bb4d211779fe5；
/var/www/letsencrypt已经存在且root0755、非软链。首次默认Python cafile检查
run38765774173失败记录保留，修正为检查已有发行版CA路径后成功，无安装或盲重试。
候选已消除CA占位符并绑定现有路径；相应本地测试仅用假CA替换以验证TLS行为。

W03清单交付完成；W04配置开发/测试与最终制品送独立审核。W05只完成上述
只读前置，证书签发/续期、生产配置安装/reload、W06实机整站、DNS仍未执行。
新增数据来自GitHub自主取证，没有让Owner重新采集或导出。所有生产门禁继续HOLD。

### 9.7 Owner最新源站约束（2026-10-16 00:12 Asia/Shanghai，优先于上述内容选择）

Owner明确：昨天由Work重做的官网包由Owner直接在服务器上传执行，代码位于英国服务器；当前官网必须保留，不得覆盖。**网站内容权威以服务器实际部署文件为准，不以GitHub分支、历史归档或CI制品为准。** GitHub仅用于迁移工具、配置、审计与证据记录。

当前尚未由本执行窗口直接核实英国实际部署目录、Work包对应版本及其与公开官网、国内stage的逐文件一致性。不得以历史Work V2名称、0363531源提交、1187文件数量、首页200或既有RG1通过，推断其必然等于Owner最新服务器版本。也不得推断历史包已经过期；先取服务器事实再判断。

执行约束：
- 保留英国/东京当前网站、国内既有stage与所有历史归档，不覆盖、不同步删除、不改变current指针。
- W01/W02历史准确制品与RG1验收结论保留；它们是否适用于Owner当前实际官网，新增“服务器内容基准核对”仍PENDING。
- W04最小反代配置可继续作为配置候选核验；其中指向国内既有stage的root不构成当前官网内容选择批准。
- 下一内容节点：通过已有获准通道只读取服务器真实部署路径/发布标识/文件Manifest，并对照实际公网及国内stage；没有取得此证据前，网站内容安装、切换和DNS迁移HOLD。
- 不恢复英国已隔离Runner/P2，不启动OpenClaw，不新增SSH密钥或通用sudo。优先复用已有服务器回执及可用获准通道；GitHub无法读取的主机事实必须明确标记缺口。
- 截至本约束记录，未执行生产网站覆盖、current变更、Nginx安装/reload、证书签发或DNS切换。

### 9.8 最终配置制品复算与统一送审状态（2026-10-16）

Owner要求继续执行、最后统一送审。未发起逐点审核，不将本检查点当完整迁移交付。

最小Nginx准确配置候选：e2bee8003e03ebf6025cf5fbc91086068c5fb3b6。
Push CI run38766304600/job116530278769 SUCCESS，82/82（含真实临时Nginx与假TLS上游测试），旧采集边界2/2；OAuth准确哈希未变，45项未重复运行。测试不代表国内生产443、英国内容或真实动态业务验收。

本窗口实际下载Artifact11988447790原始ZIP，复算：
- ZIP SHA256 ee48bfe4aa6b90d1b7e7622e0227c395d306dc6f27304db3bc696bef3a8e149f
- 内层TAR.GZ SHA256 c4677bc057e0cb6fb7a5f2cead9b78399f06abe75006bac9abfa22f1f5e74aa4
- REVIEW_BINDING准确提交e2bee800，17/17文件SHA匹配，额外文件0、特殊文件0。
这是开发方制品核验，不是独立审核结论。归档内计划为e2bee800时版本，Owner实际服务器优先约束以其后2f1c6f6a及本节为准，不可用旧归档计划绕过9.7。

统一送审尚未提交：英国实际部署内容基准未直接核实；现有GitHub连接不能直接读取英国主机文件，已知英国Runner停止/隔离，禁止为取证擅自恢复。无已接入admin/root或DNS写通道。上述缺口不能以GitHub源码/制品推断补齐。
尚未执行生产网站覆盖、指针切换、安装/reload、证书签发、DNS变更或东京退役。后续集中审核应同时包含服务器内容基准、配置制品、证书/续期、真实路由验收及回滚；未完成项不得写PASS。

### 9.9 服务器实际内容核对完成（2026-10-16 00:35 Asia/Shanghai）

Owner英国admin只读搜索：指定/tmp、/home/admin、/home/xuanjun_dev、/opt、/var/backups、/root内深度9的包名搜索，MATCHES=0、EXIT=0。仅证明限定搜索未命中，不声称英国全盘无网站。

随后本窗口自主通过东京/国内既有非root Runner取得实际文件证据：
- 初次定位commit8230ef7382b921f296a0ebbbc882ec775f1d1f25，run38770056799。
- 全文件核对commitd9deff2f31ca8a96a36928d720c80a2aef356e27，run38770145783；Tokyo job116543508444、Domestic job116543507998。
- Tokio /tmp找到Owner截图对应website-public-copy-review.patch、两份相同copy-update包及language-guard包。
- copy-update SHA256=733751a5505add8b42d1dcde697865f01f7e3e004f62e6cbebbd1d72c9c8a2cc。
- language-guard SHA256=b4ec4abf57e95c6bf460632f798471d717078c89e6be5102526c70bd47a2212f。
- 两机包搜索存在权限受限，search_exit=1（Tokyo269处、Domestic252处Permission denied）；禁止据此声明全盘没有其他包。已找到的包及以下可读实际站点文件有直接证据。

实际Tokyo站点/var/www/wenwenwenyiyiyi.work：1187文件、11090003字节。
实际Domestic /var/www/wenwenwenyiyiyi.work/current/public解析至已验收recovery-stage：1187文件、11090700字节。
逐文件相对路径及SHA256比较：新增0、缺失0、相同1186、差异1。
唯一差异assets/tiktok-integration.js：
Tokyo=01f08d5021d6b232f7f67f775c5cecd430e8a2713551cf8cea24277954ba4c0d；
Domestic=6fa38b952b70862e5a835ae79e4eedfe4b3d0323a8d819bbfb7ef81bddd8aa67（原已批准overlay）。
index.html两机均4cdaa871b46fb8f62a5527a81724a9a955beed76542dba922bb4ac9779e90f20；yunhui.css、yunhui.js亦完全相同。

结论以本次服务器实读为准：国内既有候选保留当前已确认Tokyo实际官网全部1187路径，1186文件字节相同，仅有历史批准TikTok修正；没有证据需要重新构建官网、上传旧包覆盖或重做RG1。
9.7保护Owner官网约束继续有效；其“内容基准未直接核实”缺口对本次实际Tokyo现网/国内候选比对已关闭，不扩大为英国全盘来源或另一个未知版本已核实。
现场内容不会因本核对自动替换。生产apex配置、证书/续期、W06真实路由、DNS和东京退役均未执行；统一送审仍需完整发布/回滚与现场门禁，不能报迁移完成。


### 9.10 夜间自动现场证据（2026-10-16 CST；仅增量）

Owner 已授权夜间继续自主获取两地证据。通过原 GitHub 非 root Runner 执行；无 sudo、新权限、生产文件修改、DNS 修改、服务重启或真实业务写请求。已通过的 83 项、OAuth45、两地115静态检查全部继承。

- 边界采集提交 `81855c0e3feb3244c70be1a219be9fe1f94ba485`，Run [38776953939](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38776953939)。
  - 国内 Job116566967318，东京 Job116566967626；两者执行成功，不等于动态验收通过。
  - 11项职责各 baseline/spoofed_source HEAD，共44个两地请求。10项各502；Telegram无效路径405。无重定向、无Set-Cookie。响应相同只能证明这组方法的外部行为，不能证明后台头覆盖或GET/POST鉴权通过。
  - OAuth start/callback GET、凭据提交、disconnect POST、消息/支付/交易全部 NOT_TESTED，未调用。
  - 东京生产入口文件 SHA256 `528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006`，与Owner原文件一致；仅do_GET/do_POST。
  - 东京153个可读Python文件记录路径、哈希及IP相关token行号，未导出源码内容或凭据。词匹配不等于完整调用链分析。
  - 国内受审代理配置真实哈希 `307930ba9ea726a34a7c0365d8a7446cd2967c8331682e0b9a52ac60e3936201`，X-Real-IP/X-Forwarded-For覆盖为$remote_addr，X-Forwarded-Proto=https，固定Host/SNI、上游证书校验on、proxy_next_upstream=off。东京又覆盖X-Real-IP=$remote_addr；未发现real_ip信任配置。不能据此宣称所有外围服务均无客户端IP依赖。

- 针对502的增量定位提交 `a7643ed9d28a7c01bb5e75d707bd5e08f153cc7a`，Run [38777134734](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38777134734)：
  - 东京 Job116567589539，国内 Job116567589902。
  - 两地分别访问国内/东京 /healthz GET均200，正文SHA256 `a12b7cb43c9d9134b5bb1b35e9096b66775d9e92e7611d1cc92b02edd6782a87`。同路径HEAD均502。
  - 东京127.0.0.1:18080 GET200，HEAD RemoteDisconnected；服务active/running，MainPID2023577未变，18080仍监听。支持“旧后端不支持方法的处理异常”，不支持“后台整体停机”判断。
  - 原入口log_message第1207附近将带%s的格式串全部参数替换为字符串；BaseHTTPRequestHandler的错误日志含%d和%s，独立最小表达式复现TypeError。与HEAD直连断开相符；未读取生产异常栈，因果诊断仍标为高置信待独立复核，未修改旧后台。
  - 东京nginx.conf当前SHA256 `d7cf6b60d85b5a6b36df7437a26249d643bc756b4f6ac31fa1521ef1487dcef3`；新增ACME include恰好1次。移除该单行后的字节SHA256严格恢复原 `80b49c552823e5684ec35abdf23af52e37081620a654124320e0c3a7974242f4`。ACME独立配置SHA256仍为受审190f7180…d27383；wecom.conf仍ca380c77…9931c0。关闭实际单行include差异证据缺口，root私有备份内容仍沿用Owner证据。

| 动态职责 | 两地 HEAD baseline/伪造来源头 | 业务方法/鉴权 |
| --- | --- | --- |
| /p/ | 502 / 502 | NOT_TESTED |
| /submit/douyin | 502 / 502 | NOT_TESTED |
| /submit/tiktok | 502 / 502 | NOT_TESTED |
| /integrations/douyin/oauth/callback | 502 / 502 | NOT_TESTED |
| /integrations/tiktok/oauth/start | 502 / 502 | NOT_TESTED |
| /integrations/tiktok/oauth/callback | 502 / 502 | NOT_TESTED |
| /integrations/tiktok/status | 502 / 502 | NOT_TESTED |
| /integrations/tiktok/disconnect | 502 / 502 | NOT_TESTED |
| /healthz | 502 / 502；GET200 | GET只读通过 |
| /telegram-webhook/ | 405 / 405（固定无效后缀） | 真实POST/密钥鉴权 NOT_TESTED |
| /telegram-canary/status | 502 / 502 | NOT_TESTED |

DNS两台公共解析一致：A=47.245.53.152，AAAA应答为空，NS=celine.ns.cloudflare.com/chris.ns.cloudflare.com，SOA serial2417364535。递归答复TTL=10是观测值，**不是DNS控制台配置TTL**。未获得Cloudflare记录ID、proxy状态、原配置TTL与精确回滚绑定，不放行DNS。AAAA空答复也不冒充权威不存在证明。

IP初步分类：入口client_address用于日志；入口X-Forwarded-Proto用于Origin构造；secure_secrets_portal可读历史代码限流按session/form计数；交易模块ip_whitelist描述外部交易所密钥IP限制，不能据词匹配判断受本次域名入口影响。完整转移调用链、外围WAF与日志使用方仍UNKNOWN。Owner未接受临时审计差异。

终态：DNS_RELEASE=HOLD；DYNAMIC_ACCEPTANCE=NOT_PASS（旧HEAD错误路径异常待处理/裁定）；东京退役HOLD；Work官网未改。夜间续接仅增量处理上述证据，禁止反复重跑已通过检查或自批准生产。


### 9.11 2026-10-16 02:30 CST：权威DNS、精确日志函数及安全GET增量

本节仅补缺口，不重复9.10的44次HEAD、既有静态115/83/45检查。准确探针提交 `c2caa95967fbc8f51129cec064ce5c4358066b1a`；Run [38785334400](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38785334400)，国内Job116595748814、东京Job116595748929均SUCCESS。成功仅表示取证执行完成。

**DNS原资料复用与实时权威核对：**
重新读取原已核验回执[6184420192](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/122#issuecomment-6184420192)，没有要求Owner重新提供资料。原Cloudflare导出SHA256 `531bc71f3d5eff6cb7ad5c7e6aea3912578a8a91ff8ade740ef2e40d2e7eb771`，导出标注2026-10-15 04:27:26（未声明时区）。当时12条清单已经通过；A/CNAME的cf-proxied:false、TTL字段1均已有**历史**证据。9.10缺口应理解为“切换前当前管理面状态未重验”，不得误写为从未提供过代理/TTL资料。
两台Runner分别直接查询celine.ns.cloudflare.com和chris.ns.cloudflare.com：
- A：均NOERROR、AA、47.245.53.152、权威应答TTL300。
- AAAA：均NOERROR、AA、ANSWER0及SOA，serial2417364535、negative TTL1800。关闭“只有递归空答复”的证据缺口；不等于管理面记录枚举已完成。
- 原导出TTL字段1、权威TTL300和此前递归TTL10分别保存，不混为同一字段。
- 原apex回滚基线可绑定：A/47.245.53.152、历史proxied:false、历史导出TTL1；待发布时必须通过已授权管理面核对该单条当前值/记录身份/代理和TTL。目标只改apex至47.101.152.210，禁止重新导入区域或改其他11条。此处是回滚基线，未执行DNS修改，也没有获得当前Cloudflare账户控制权。

**旧HEAD日志异常的精确源码复现：**
在东京读取哈希仍为528a3b5b…b5006的生产入口，用AST仅提取PortalHandler.log_message，独立命名空间执行其精确函数；没有import生产程序、数据库或执行启动代码。
字符串格式请求日志正常；标准错误日志混合%d/%s输入抛TypeError。它将数值参数也替换为[REDACTED]，因此%d失配。此前只验证最小表达式，本次已验证实际函数。结合直连HEAD断开/GET200，旧错误日志缺陷证据进一步收敛。未读取生产异常栈、未修复或重启旧服务；任何修复仍需准确最小补丁、回归和增量审核，不能把它说成国内反代新引入的问题。

**安全GET拒绝：**
两台分别请求/submit/douyin、/submit/tiktok、/integrations/tiktok/disconnect及固定非法/integrations/tiktok/pr122-invalid-readonly；每条baseline及wrong_origin_and_source共16请求，全部404、无Set-Cookie。前三条两地正文SHA一致；非法路径的404错误页字节两地不同，未标内容等价。错误Origin/XFF/XRealIP/XFP组合没有把这些GET变为成功，但不证明POST的CSRF/认证，也不单独证明上游收到的具体头。未访问/p/会话、OAuth start/callback GET、真实状态或任何POST写请求。

**IP调用链证据的真实范围：**
东京从入口递归解析本地import模块，取得42个模块哈希、import关系和IP/动态解析位置；read_error0、未触及250上限。入口client_address仅在log_message，X-Forwarded-Proto在_origin；portal限流命中_validate_submit_session。发现database/repositories/__init__.py和database/models/__init__.py的__getattr__/__import__懒加载，静态import递归尚未展开这些分支，因此不能声称完整闭包通过。外部cryptography/SQLAlchemy及标准库也未被此静态扫描审核。
下一可自主动作是按实际入口使用的符号解析上述懒加载映射及其本地目标，继续只读AST/哈希，不执行生产import、不查询数据库或读取凭据。外围WAF、日志使用方及Owner临时IP审计差异接受仍缺证据。

截至本节：DNS_RELEASE=HOLD；动态鉴权/真实业务写验收仍NOT_TESTED；东京退役HOLD；原生产配置制品312efdd3及官网/current未改。等待独立审核只消费增量，不能将探针提交或CI SUCCESS当生产批准。


### 9.12 2026-10-16：数据库懒加载覆盖补齐（限定源码证据）

本轮先读取PR122自6199294955之后回执：未见新的独立发布结论。沿用9.11，不重跑DNS、静态、HEAD或16条安全GET，不修改已批准配置/官网/current。准确探针提交 `8e7f8db4142a5b5acde406019a5dd114a285ec20`；[Run38794274496](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38794274496)，东京Job116626465013 SUCCESS。英国、韩国、国内及原dispatch作业SKIPPED。

为消除上一轮仅递归import漏过懒加载数据库模块的风险，本次采用**保守扩大源码集合**，不是执行__getattr__/__import__：从实际入口解析本地imports，同时纳入database顶层、models及repositories全部可读.py，再递归这些文件本地依赖。最终83模块（其中数据库50），pending0、read_errors0、未触及300文件/35秒上限。每个文件均记录SHA256和imports；生产入口哈希仍528a3b5b…b5006。没有生产import、没有业务数据库/凭据读取、没有网络请求或服务操作。

必须保留工具限制：符号导出映射自动提取器仅匹配含database.的顶层字面量，返回lazy_exports=[]，**不等于没有懒加载，也不能声称每个动态目标已语义求值**。本次通过覆盖整个数据库源码集合而非运行动态分派补足本地文件范围。仍记录三处动态调用：models/__init__.py的__getattr__第117行；repositories/__init__.py的__getattr__第36行；trading_integration_repository.py的count_billing_operations_job_runs_by_status第1440行。外部库、运行时注入和外围WAF不在本次证明范围。

| 分类 | 直接证据 | 能得出的结论 |
| --- | --- | --- |
| AUDIT_ONLY（入口源码） | secure_secrets_portal_server.py第1207行，client_address在log_message | 实际入口里所扫描的客户端对端地址使用是日志；不是Owner已经接受IP审计差异 |
| Origin构造 | 同入口第1237行，X-Forwarded-Proto在_origin | 与可信代理头覆盖有关，不能用“IP仅日志”忽略协议头语义 |
| RATE_LIMIT（非IP源码符号） | secure_secrets_portal.py第1668行_validate_submit_session；session.attempts、form_key、count、max_attempts_per_form | 限流函数符号指向会话/表单计数；未发现该函数使用remote/client IP，不等于真实POST安全验收通过 |
| 数据库本地源码集合 | 本轮50个数据库.py中无所扫描IP属性/键命中 | 关闭“只读到懒加载入口，漏扫其目录内源码”的范围缺口；不是任意动态运行行为无IP依赖的证明 |
| AUTH/SECURITY（整体） | 83模块扫描未见更多客户端来源IP属性/键命中 | NO_ADDITIONAL_DEPENDENCY_OBSERVED，不能升级为全系统NO_DEPENDENCY |
| 外围WAF、第三方库、日志使用方 | 本通道无对应运行策略/消费方验收 | UNKNOWN，不能由开发方自接受风险 |

旧HEAD错误已由9.11精确函数复现；本轮不重复复现、不向生产写补丁、不重启。原11项职责矩阵及安全GET结果继续沿用，真实POST/授权/消息/支付/交易仍NOT_TESTED。

集中送审状态不新增批次：将本节作为6198144163/6199294955的源码证据补充，独立执行者据其范围判断，不要求重新审核未变83/45/115或生产配置制品。当前仍缺Owner对临时IP审计差异的明确接受（如采用该方案）、外围IP安全依赖闭环、旧HEAD错误路径发布影响裁定，以及DNS切换前管理面精确记录读回。DNS_RELEASE=HOLD；东京退役HOLD；不冒充网站/服务器迁移完成。

下次若无新独立回执，可安全读取国内已安装apex续期Timer的首次自动运行状态（不手动触发续期、Hook或reload），形成运行证据；已完成的源码/请求探针不盲重跑。


### 9.13 2026-10-16：首次自动续期检查回执（仅观察）

先读原PR最新回执及本计划，未见新的独立DNS放行；上轮提到的Timer首次自动运行现已取得直接非root证据。准确观察提交 `e09f66ae78d756fd2bee8d41fed8bced262538be`；[Run38801685875](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38801685875)，国内Job116652042081 SUCCESS。东京/英国/韩国/原dispatch作业均SKIPPED。只调用systemctl show、读取四个公开安装文件及一次验证证书的TLS握手；无sudo、无手动续期、无service start、无Hook执行、无reload、无DNS修改。

- Timer xuanjun-apex-cert-renew.timer：loaded、enabled、active/waiting。
- LastTriggerUSec：2026-10-16 03:40:31 CST。
- Service开始03:40:31、结束03:40:33 CST；Result=success、ExecMainCode=1（CLD_EXITED）、ExecMainStatus=0。
- Type=oneshot服务检查完成后inactive/dead是正常终态，不误报为后台故障。
- 下次计划时间：2026-10-16 15:43:00 CST（当时观测，带随机延迟）。
- InvocationID：94ae2e4cfd6d40b8b6dc92e08932534a，绑定这次实际服务运行。
- 当前国内证书：系统CA/SNI验证通过，SAN=wenwenwenyiyiyi.work，serial=05B84F2C5179B9BF9C474D5A0085A57EEF4D；notBefore=2026-10-15 16:03:59 UTC，notAfter=2027-01-13 16:03:58 UTC。仅读取公开TLS证书，不触碰私钥。

| 已安装文件 | SHA256 | Owner/mode |
| --- | --- | --- |
| /usr/local/libexec/xuanjun-apex-cert-renew | cb2a9e645cff03e04c667c1001b3eec627119a0498395b013324de909d9f357e | root:root 0755 |
| /usr/local/libexec/xuanjun-apex-nginx-deploy-hook | adb7d7efd5c4255b7aabefd3a0bc74ae7af0df221e32fcf92bf7044bc13b6be8 | root:root 0755 |
| /etc/systemd/system/xuanjun-apex-cert-renew.service | d68bc892873d52f8cf8a9ac95c09938c10564abba6f9bcf82d713a2a76a005b8 | root:root 0644 |
| /etc/systemd/system/xuanjun-apex-cert-renew.timer | 4ce36b58ba0e599d37458f3aecb0c3c20a588175ffca66834228d405da73807e | root:root 0644 |

另直接读取已批准准确提交312efdd3eb4d24ff1fceecc480c4ba302bf22073的对应四份源码，并重新计算其SHA256，与上述现场4/4相同；四个现场文件均非symlink。这是安装后具体四文件绑定核对，不重打包或重跑83项测试。

结论限于**首次自动续期检查执行成功**。Certbot renew在证书未到期时可成功退出而不续签；当前无证据证明这次更换了serial/到期日，故ACTUAL_CERTIFICATE_RENEWAL=NOT_ESTABLISHED，不能称“首次真实续签已成功”，也不能推断这次deploy-hook已经运行。既有Owner dry-run和Hook手工执行证据继续继承。

至此，9.10—9.13的主动缺口取证已保存原PR。后续没有新HEAD、新独立审核或新事实时，不再推送同样探针、不重复运行或追加同义回执。剩余为独立审核对旧HEAD缺陷及动态边界的裁定、外围IP安全依赖/日志审计差异闭环（必要时Owner明确接受），以及DNS变更前已授权管理面的当前单条配置核对。当前会话无admin/root或Cloudflare管理面接入，不扩权，不读取/搬用其他流程凭据，不为获取权限启动OpenClaw或英国P2。

DNS_RELEASE=HOLD；东京退役HOLD；Work官网/current、桥接/隧道、PR99/Finance均不因本观察变更。网站入口切换与整体服务器迁移仍未完成，不用自动检查成功替代生产放行。


### 9.14 2026-10-16：Owner要求继续W01—W10；W06最小整改已交付

Owner询问十节点进展并明确要求继续实际执行。当前节点状态以下表为准，覆盖§9.2中早期状态文字，但不删除历史证据。

| 节点 | 当前状态 | 已完成与剩余 |
| --- | --- | --- |
| W01 现有官网/制品基线 | 完成（已确认服务器范围） | 实际服务器1187路径及1186相同+批准TikTok差异已绑定；保护Work官网 |
| W02 国内静态隔离验收 | 完成 | 原RG1/stage/指针及本地验收继承 |
| W03 全路由责任清单 | 完成 | 75条规则、11动态职责及109历史URL身份绑定 |
| W04 最小Nginx候选及审核 | 完成（限定范围） | 精确312efdd3配置制品及独立审核继承；不是DNS批准 |
| W05 证书/续期/HTTP | 完成（已验收范围） | 国内HTTPS、dry-run、Hook、Timer、HTTP308/ACME；03:40自动检查成功，实际换证未证实且非当前到期必需 |
| W06 切DNS前整站验收 | 部分完成；日志修复及R4临时遏制已实机执行 | 原静态115及限定动态证据继承；日志补丁已审生产通过；R4一次root安装/四次403及两地公开证据已获6206210165限定实机PASS；IP审计/外围动态边界仍未闭环 |
| W07 网站切换放行 | HOLD | 原独立审核尚未批准DNS，不能自签 |
| W08 DNS切换 | 未执行 | 管理面当前单条核对/实际变更尚未执行 |
| W09 公网切换后观察 | 未执行 | 等W08；预发布直连校验不等于公网切换观察 |
| W10 网站迁移关闭 | 未完成 | 等W06—W09全部满足；东京后台依赖仍保留 |

本轮完成的实际整改候选（**未应用生产**）：
- 准确提交 `ce211a606e82845bfe4d7a6e3d511f3872d53147`，tree `efb065512863f57692a6e8b207ede3ed8c04c32f`。
- 仅改变现有生产Portal的log_message函数。保留数值状态参数，其余参数脱敏；内部格式异常退回脱敏信息；错误请求URL解析失败不再让日志函数抛错。没有增加do_HEAD或放宽方法，未支持方法恢复为标准501而非上游断开造成502。
- 原源文件SHA256 `528a3b5bd13dfbb5067731b3f0ae1305b28cba888658aacc09bf64cbed8b5006`；候选源SHA256 `d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0`。
- 从Owner已上传原文件取回字节并复算，哈希吻合。内存builder要求准确原哈希，只替换唯一日志方法；源码不符即拒绝，没有安装CLI或生产写操作。
- 新候选目录deploy/pr122-portal-log-fix与既有已批准网站/配置制品分开；不改原网站或OAuth包。不能用新OAuth架构替换实际旧Portal来解决单个日志问题，所以采用此最小局部修复。
- 本地16/16 PASS，包含原版混合%d/%s TypeError与实际隔离HTTP HEAD断开复现；修正版HEAD/OPTIONS/DELETE/PATCH/TRACE/CONNECT返回501，GET200；参数脱敏、畸形格式、错误URL、源哈希拒绝及除日志方法外AST/字节不变。
- 东京既有非root Runner对实际/opt/trading-system/scripts/secure_secrets_portal_server.py取源，同样16/16 PASS。Run [38826287071](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38826287071)，Job116734398956 SUCCESS，准确checkout ce211a60。日志PR122_LOG_FIX_RECEIPT明确PASS_ISOLATED_ONLY，production_source_write=false、service_restart=false、production_imports=false、dns_change=false。
- 测试只提取日志AST，在临时127.0.0.1随机端口的假HTTP服务中执行；不运行生产app、不查询数据库、不发送真实业务请求，不代表修复已在18080运行。
- Artifact12014899180，ZIP12778字节，SHA256 `76605c4c71c341770a12881f7182f0c12161fae58e2b6b1e38c5037ae41f08ad`。本执行方实际下载原ZIP复算，6文件=5份绑定输入+1份REVIEW_BINDING；5/5哈希一致，额外文件0。此为开发方核验，不冒充独立审核。
- 既有PR会按其累计diff自动触发其他托管工作流；本次只新增上述16项针对回归，不以自动重跑的历史套件替代既有精确制品审核，也不重新构建官网或改变已批准312efdd3发布范围。

继续顺序：同一原PR集中增量复核上述6文件/实际日志；接受后通过既有批准root路径绑定备份、准确原/新哈希及回滚，再执行原子安装/服务重启及目标动态复验。当前会话没有已接入admin/root或DNS管理面，不能从非root测试推断有生产执行权。外围IP依赖、Owner对临时审计差异的明确接受（如采用）、实际动态鉴权和DNS切换门禁依然独立保留。

准确结论：W01—W05完成，正在W06；本轮已从取证推进到最小整改候选、真实Runner针对测试及制品交付。W07—W10未完成。未切DNS，未停止东京，未覆盖Work官网。


### 9.15 2026-10-16：最小补丁独审通过，Owner授予长期运维授权

正式独审PR122#6204793589已读取：精确ce211a60源码/制品通过，东京16项为隔离证据；实际生产修复NOT_EXECUTED，DNS及退役HOLD。无需重审未变补丁或网站。

两次非root只读通道核查：2422d6f0 Run38826917515/Job116736405728，原源SHA仍528a3b5b…b5006、服务active、原PID2023577；2ded20f9 Run38827036234/Job116736775569确认githubrunner现有sudo仅固定/usr/local/sbin/xuanjun-migration-inspect-v1，无法应用本次补丁或重启。没有把非root取证当作root验收。

Owner明确要求提供放权步骤，并补充“给你授权长期的，不只是网站迁移，后面还会有服务器迁移”。登记为国内/东京网站与服务器迁移、受控部署、维护、备份及回滚的长期可撤销授权。DNS发布、真实业务写、东京退役等门禁仍独立；不恢复英国P2、不涉及PR99/Finance、不改桥接隧道。

本次新增技术适配器位于deploy/pr122-portal-log-capability：root私有grant/receipt、摘要绑定sudoers、status/apply/rollback/revoke四个固定命令，不设到期；当前只实现东京精确日志补丁，尚不具备国内或任意服务器任务的通用root能力。未来任务沿用Owner长期授权，需扩展并审查具体动作。安装器内嵌准确helper字节，先校验主机/UID/旧源/目录身份和visudo语法，最后发布规则，安装仅status，不自动apply/restart。apply和rollback各一次，异常保留证据，禁止盲重试。

本地20项文件系统/回执生命周期测试PASS；真实原源和synthetic分别验证，当前容器UID映射的测试替代仅在测试模块内。真实visudo解析规则、内嵌payload字节匹配PASS。托管CI仅运行synthetic隔离测试和规则检查，不代表东京root或业务验收。新入口本身属于新增执行机制复核范围，不能用6204793589冒充已独审。原补丁16、OAuth45、配置83、静态115不重跑。

ROOT_CAPABILITY_INSTALL=NOT_EXECUTED；PATCH_PRODUCTION_INSTALL=NOT_EXECUTED；W06仍部分完成；DNS_RELEASE=HOLD；TOKYO_RETIREMENT=HOLD。首次接入需要Owner现有东京admin终端安装固定入口一次，此后现有GitHub Runner可调用已注册命令。生产官网/current与批准312efdd3配置制品未改。



### 9.16 2026-10-16 08:21 CST：Owner首次安装长期入口成功，启动单次已审补丁执行

Owner在东京admin终端运行准确4975724d安装器，SHA256 e95d2c08…f1b3a0通过，原sudoers/新增规则visudo均通过；实际输出PERSISTENT_SCOPED_CHANNEL_READY、READY/apply_started=false/rollback_started=false。该回执为Owner root实机证据，安装未应用补丁、未重启服务。

本次沿用原v27工作流及同一concurrency组，由东京githubrunner调用已安装摘要绑定helper，不复制新的root脚本、不改权限规则。执行前核验实际host/UID/helper root身份及完整SHA2560e61a4ca…2cbcbe，固定status必须READY才允许调用一次apply；异常不重试、不自动回滚、不改变桥接隧道/DNS/网站/current。准确原源备份、候选替换、仅Portal一次重启及两地GET/HEAD健康检查由固定helper执行。此段记录执行意图，最终以绑定本次job的原始PR122_ROOT_EXECUTION_RECEIPT为准；尚不预报生产PASS。

补丁独审6204793589和Owner长期授权已具备；新增固定入口的集中复核6205089607尚无独立结论，不将20项synthetic或Owner安装成功冒充完整执行机制独审通过。DNS_RELEASE=HOLD、东京退役HOLD继续。


### 9.17 2026-10-16 08:23 CST：东京生产最小日志补丁已真实应用

准确执行提交d338fb057b9618f1356ce877c2453f9309423c5f；Run38829135481 / Job116743548144 SUCCESS。已读取原始日志PR122_ROOT_EXECUTION_RECEIPT，不只依赖job绿灯。实际Tokyo root helper哈希0e61a4ca…2cbcbe，执行前READY/apply_started=false。apply本job调用1次，exit0，root回执LIVE_HEAD_GET_PASS；原源528a3b5b…b5006、候选d5ab592a…bbdf0，backup=/var/lib/xuanjun-pr122-portal-logfix-capability/source.before.py。source_replaced_for=apply、restart_attempted_for=apply；rollback_started=false。固定helper只执行一次Portal重启。

实际两地TLS校验后/healthz：东京47.245.53.152 GET200/HEAD501；国内47.101.152.210 GET200/HEAD501。恢复原不支持方法501，旧502错误路径已在真实服务修复。新执行入口本身的独审仍PENDING；不冒充6204793589批准了新机制。

回执Artifact12015874337（988字节）及GitHub元数据digest sha256:604f9fc85bac066d33aef335501ffb937dab92c3116ee792ab5fe0557023e782；此处digest来源为GitHub元数据，未据此冒充独立复算。

立即将原工作流push job中的apply调用移除，改为两地非root部署后核验：新源哈希/owner/mode/新PID、根入口status、Work首页与国内current不变、11项HEAD baseline/spoofed_source。HEAD只证明不支持方法边界，不能替代GET/POST认证；OAuth GET/业务写继续禁用。执行结果另附真实回执，不提前PASS。

PATCH_PRODUCTION_INSTALL=EXECUTED_PASS_TARGETED_HEALTH；W06仍部分完成（动态业务鉴权、IP审计差异及外围策略未闭环）；W07/DNS_RELEASE=HOLD；东京后台继续保留。未改网站内容/current、DNS、桥接隧道、英国P2或Finance。原未执行文字保留为历史，仅此新增事实覆盖补丁状态。


### 9.18 2026-10-16：部署后两地HEAD边界通过；鉴权缺口具体化

准确只读核验提交f5625637f5f0e8ef78bb67dcdc8c2a9d6bd01a00；Run38829320821。东京Job116744154336、国内Job116744154573均SUCCESS；已读两台原始日志PR122_POSTFIX_BOUNDARY_RECEIPT。各11项职责x2组头=22次，两地共44次：10项各501/501，Telegram固定非法后缀405/405；无重定向、无Set-Cookie，TLS验证通过。此为POST_FIX_METHOD_BOUNDARY_PASS，HEAD不证明GET/POST认证，也不证明真实客户端IP头消费语义。OAuth start/callback GET、任何真实POST/消息/支付/交易均未调用。

东京部署源实际SHA256=d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0，admin1000:1000/0755/regular/nlink1；Portal active/running/Useradmin，新PID3075458（旧2023577）。root固定status=LIVE_HEAD_GET_PASS，rollback_started=false。东京及国内首页SHA256均保持4cdaa871b46fb8f62a5527a81724a9a955beed76542dba922bb4ac9779e90f20，国内current仍pr122-d8b08ed-recovery-stage。只核对本次保护对象，不重跑整套静态115/83/OAuth45。原工作流apply job已移除，后续此版本只有非写核验。

**鉴权边界新增具体发现（旧代码既有，不是日志补丁引入）：**
当前准确生产源的do_POST在/integrations/tiktok/disconnect分支直接实例化生命周期存储并disconnect/record_audit/200，没有显式Origin/session/CSRF校验。为遵守禁止真实断开，未发任何POST。仅从实际候选字节AST提取do_POST，以fake store/audit/response执行；空headers、无session/body时FAKE_DISCONNECT_CALLED并FAKE_RESPONSE200。没有import生产app、没有真实存储/凭据/DB操作。证据仅证明处理函数分支缺显式鉴权，外层代理/WAF全链可利用性未作实机写测试，不冒充已被攻击或全系统无防护。

复用原东京Job116566967626的Nginx只读收据：nginx.conf与所含ACME/wecom配置未记录auth_basic/auth_request/allow/deny；当前312efdd3已审国内location也直接代理disconnect。外围策略最新状态仍UNKNOWN。新增finding详见evidence/pr122-portal-log-fix/DISCONNECT_AUTH_STATIC_FINDING_20261016.json，供同一次集中独审判定发布影响和最小整改；不擅改既有批准生产配置或调用真实断开。

所有11项业务方法的限制继续逐项继承：/p/真实会话、两项submit POST、三项OAuth GET、status真实状态、disconnect POST、Telegram POST/密钥及canary状态均NOT_TESTED；只有healthz GET实机200。以前安全GET拒绝证据继续有效，不用HEAD501冒充认证通过。IP依赖源码范围沿用§9.12，外围WAF/日志使用方和Owner审计差异接受未关闭；DNS当前管理面记录ID/代理/TTL/回滚核对未取得。DNS_RELEASE=HOLD、东京退役HOLD，网站入口和整体服务器迁移尚未完成。


### 9.19 2026-10-16：R4开发责任及最小遏制候选（范围待裁定）

原开发方就是本ChatGPT开发窗口，继续原PR122/原分支负责，不转OpenClaw、不另建队列。已读取6205227893：日志实机验收与44HEAD继承PASS，R4 High需处理。现有旧Portal没有可直接复用的已认证断开账号授权链；凭据提交会话或未部署的OAuth候选不等于登录身份/账号所有权。

为响应Owner最小化迁移，新增独立候选deploy/pr122-r4-disconnect-containment：准确源d5ab592a…bbdf0，仅将旧HTTP disconnect分支替换为固定403、operation_performed=false及常量安全拒绝日志，在Token存储构造/请求体读取/账号绑定/业务audit之前返回。全部调用者均拒绝，其他字节不变。候选哈希57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1。

本地18项实际handler AST隔离测试通过，覆盖原漏洞复现、无登录/错账号/CSRF/Origin/伪造代理头、重复/并发拒绝、存储失败不可达、脱敏、精确哈希和真实临时loopback403。所有拒绝store/disconnect/business-audit次数0；只有常量安全拒绝日志。正向授权断开与其事务恢复没有实现，不将全拒绝测试冒充完整R4鉴权修复。东京Runner将对实际已部署源运行同18项并生成准确制品；CI结果以实际日志为准。

此为**暂停该HTTP写能力的受限迁移候选**，需要同次独审明确接受该发布范围；不能预设功能退场已获批准。AUTHENTICATED_DISCONNECT=NOT_IMPLEMENTED；R4_FULL_REMEDIATION=OPEN；CONTAINMENT_SCOPE_ACCEPTANCE=PENDING；DNS_RELEASE=HOLD；东京退役HOLD。已有固定root helper仅支持已消费的日志补丁动作，不能部署此候选；源安装/服务重启/权限扩展均NOT_EXECUTED。长期Owner授权有效，动作登记与独审仍需真实技术接线。

只改原工作流push job为上述18项隔离测试，不重跑旧日志16/HEAD44/静态115/配置83/OAuth45。已通过生产网站/current与312efdd3配置不改。IP审计差异、外围依赖、DNS当前管理面核对仍须集中关闭，不能承诺未经证实的固定过审或切站时间。


### 9.20 2026-10-16：R4暂停写入候选CI及实际制品已齐备

准确候选提交d6eb4d5a941b3969d7bf43dac6053db8a8209b17，tree1b193d3df220cbedb690e8d542ec5e5a8fa99f1d。东京实际Runner Run38830466128 / Job116747832773 SUCCESS；精确checkout d6eb4d5a，使用当前生产源SHA d5ab592a…bbdf0但只提取AST，18/18 PASS、skip0；PR122_R4_CONTAINMENT_RECEIPT=PASS_ISOLATED_CONTAINMENT_ONLY。无生产import、真实disconnect、源安装、重启或DNS。其他四台原作业SKIPPED，不称通过。Feature Compliance Run38830470750 / Job116747846862已读COMPLIANCE_PASS（治理10项）。

实际下载Artifact12016977176 ZIP23440字节并复算SHA256 e3ce083c8a2fd792e83eadde5495a84bbf43e6b2cbb55aa34db2e0b0a9443c5a；ZIP恰好内层TAR+CI_RECEIPT两项。TAR22675字节，SHA25607ce8a15460ea8c280c36c02825fce73b0b947b1dfde9e52452e306e39acf8b4；8项=7份绑定文件+REVIEW_BINDING，7/7哈希匹配，无额外/链接/特殊类型。绑定含builder、18项测试、只改分支patch、README、workflow、governance和开发说明。此为开发方下载复算，不冒充独审。

本轮候选准备已完成并可集中审核；其目标仍是请求**暂停HTTP disconnect能力**的范围裁定，不是正向授权断开已实现。R4_FULL_REMEDIATION=OPEN；CONTAINMENT_SCOPE_ACCEPTANCE=PENDING；PRODUCTION_INSTALL=NOT_EXECUTED。日志已审生产修复、网站/HTTPS/现有current继续保持。待审核方裁定此最小范围及其他既有IP/DNS门禁，不承诺固定切站时间、不直接切DNS。


### 9.21 2026-10-16：6205371670已接收，R4受控安装候选准备完成

正式独审接受临时关闭HTTP断开写能力；完整鉴权仍OPEN且不阻断该缩减范围。原18测试/源码审查继承；原12016977176制品全字节独审、实际安装/实机验收与DNS仍PENDING。当前会话继续原开发任务，不自签发布、不切DNS。

新增deploy/pr122-r4-controlled-install：独立Owner-root固定脚本（没有新sudoers或权限扩展），仅复用已安装完整SHA0e61a4ca…2cbcbe的事务引擎并在内存绑定准确R4 builder1afc01c6…a0d6d93、原源d5ab592a、新源57e38fc9。原helper文件/原状态不替换。脚本完整SHA883d89ef15e3c2ee6535100c71c18f69a6d39bbfce20a2a1aa9dd96f2ca94e45。固定root/admin源身份、原锁与新锁、root私有备份和一次apply标记、有界Portal重启、精确新源及新PID、两地health检查，随后才提出四个空body/合成头403负向请求。这四个安全POST属于**本次待审安装计划**，当前没有获准执行或实际调用。

新回执公开仅固定运维元数据，root0644，供现有非rootRunner后续自动读取；私有grant/receipt0600、源备份0400保留root0700目录，绝不导出Token状态或业务DB。运营说明明确：安装验收后该HTTP断开功能对包括管理员在内所有人不可用，不会主动断开现有账号。

回滚方案仅Owner显式--rollback-offline：准确候选及备份绑定、原子记录开始，先停Portal并确认PID0且18080明确ECONNREFUSED，再恢复原源并**保持Portal离线**，不自动重启已知存在R4的旧代码。Nginx/VM/静态网站不停止，但动态路由将临时不可用；此异常恢复影响须独审明确接受，当前不执行。停止不明则不恢复，异常保留现场、不盲重试。

本地20项临时root文件系统/合成源/假服务与网络测试PASS，含一次安装/禁止重试、新PID门禁、源漂移阻断POST、状态/正文/cookie拒绝、固定root代码字节、备份篡改拒绝、停服未确认不恢复、离线恢复不重启和公开回执白名单。生产root/安装/POST/服务停止重启均NOT_EXECUTED。托管CI只跑新20模型测试，不重复原18/20/44/83/45/115；最终以绑定job原始日志为准。

已知技术接入限制继续明确：长期Owner运维授权有效，既有Runner固化入口仍不能执行新R4安装动作。安装计划及制品通过前不提供生产执行命令；通过后需现有东京admin/root实际运行准确脚本，非rootRunner可自行收集已设计公开回执和验收，不要求Owner手工采数据。



### 9.22 2026-10-16：6205624143唯一I1授权准入整改候选

已接收独审：原R4源码/完整制品及旧安装制品全字节PASS；只有新root动作准入I1/HIGH继续HOLD。既有长期Owner运维授权不受影响，不自签精确候选发布批准。本增量不动已通过网站/current、312efdd3配置、旧R4分支、root helper或服务器。

新增approval_gate.py并以完整哈希绑定嵌入独立安装器；实际入口在引擎加载/锁创建前，强制读取独立Owner-root0700/0600准入锚点，核验独审评论ID及全文SHA、明确动作/版本/主机/次数/有效期/四次合成负向POST边界，再从canonical GitHub HTTPS核对精确commit/tree、实际root0400安装器字节、REVIEW_BINDING和实际ZIP制品摘要/来源commit。实际源/候选/服务核验后，执行前重查批准正文/本地字节/有效期，用O_EXCL私有持久标记一次性消费，随后才能创建R4状态或改服务。缺失/伪造/旧源码批准/过期/已消费/漂移/错误主机动作均拒绝；异常标记保留，不自动重试。

实际查明开发回执6205597052与独审6205624143共用GitHub user332398908/App1144995，故不声称作者身份可证明窗口独立。信任锚是Owner从原独审窗口独立接收的完整评论摘要，在root侧另行登记；安装器/Runner无生成锚点入口，不把开发评论当批准。这是显式Owner信任边界，不是独立审核人密码签名。ADMISSION.md描述最终审核后交接协议，本轮没有生成真实批准或生产root锚点。

紧急离线回滚需另一份action=rollback-offline精确独审回执及Owner明确接受后台中断的独立root锚点；安装批准不能授权回滚。停Portal/PID0/18080拒绝后恢复旧源并保持停止，不恢复漏洞服务。本地40项I1合成GitHub/临时root测试及20项受影响安装模型PASS；跨进程竞争和部分持久化异常保留均覆盖。原源码18/HEAD44/配置83/OAuth45/静态115不重跑。托管CI与新准确制品结果随后单独绑定，不提前写PASS。

当前I1_INCREMENT_REVIEW=PENDING；ROOT_ADMISSION_PIN=NOT_CREATED；PRODUCTION_INSTALL=NOT_EXECUTED；DNS_RELEASE=HOLD；东京退役HOLD。既有非rootRunner不能登记新root准入，仍需最终独审后实际admin/root交接，不虚构已接入。


### 9.23 2026-10-16：I1精确CI与新制品已取得，集中复审待判

准确代码提交b4b8ed3fa7dc9435e4959da11dfc335b04385100，tree3cb913dd66338da904a67d30bd22ff2827f28c62。原工作流Run38834601239 / Job116760777688已独立于本地测试读取原始日志：精确checkout b4b8ed3f，60/60 PASS、skip0（40项授权门禁 +20项受影响安装模型）；四台服务器作业均SKIPPED，不能称实机通过。Feature Compliance Run38834605641 / Job116760790857：10/10及COMPLIANCE_PASS。没有启动第二队列或额外实机测试。

开发方实际下载Artifact12017734234：ZIP56353字节 SHA256359500422ed934ad6b80bf1042c4a2a1c844987a1bde9283844ce9f22f84ed24；内层TAR55497字节 SHA25664d8e3ac64b8018b859ddf0b0fedfeccfc2da89b5d42aeed17b558a9e07f2a56；13绑定文件+REVIEW_BINDING共14项，13/13匹配，无额外文件/链接/特殊项，内容逐字节匹配精确候选本地提交输入。Binding SHA256cf2e15e6be74ba80fc4754f15a581470dc4309ad37404571fe5a5dc37999e958；实际安装器SHA256ec727883f682aa8ddf47c2e3f5fdfb1d1bac3d20909f627236553d8b0dc7dd28。此为开发方复算，不冒充独立审核通过；原已审制品不重打包或重新审核。

详细可复查证据evidence/pr122-r4-controlled-install/I1_CI_ARTIFACT_20261016.json，操作与信任边界见准确提交deploy/pr122-r4-controlled-install/ADMISSION.md。新准入代码和文档仅请求原独审窗口6205624143集中复审；真实独审执行批准/Owner root准入文件均未创建。通过后仍需原独审窗口另外给出精确限时一次动作批准及全文摘要供Owner-root固定登记；开发方不能代签。现有非rootRunner不具备新动作登记能力。

SOURCE_I1_INCREMENT=READY_FOR_REVIEW；INDEPENDENT_INSTALL_PLAN_APPROVAL=PENDING；PRODUCTION_INSTALL/POST/RESTART/ROLLBACK=NOT_EXECUTED；DNS_RELEASE=HOLD；东京退役HOLD。客户端IP审计差异/外围依赖及DNS管理面精确核对仍未关闭。Work官网/current和312efdd3生产配置未更改。此为证据断点记录，不改变安装制品中绑定的代码/文档快照或批准身份。


### 9.24 2026-10-16：独审6205924529关闭I1，转入单次安装许可

已实际读取6205924529：准确候选b4b8ed3fa7dc9435e4959da11dfc335b04385100 / tree3cb913dd66338da904a67d30bd22ff2827f28c62的I1_SOURCE_GATE_DEFECT=CLOSED_WITH_TRUST_BOUNDARY、ARTIFACT_REVIEW=PASS、HOSTED_CI_REVIEW=PASS_60_OF_60。原ZIP/TAR和13文件均由独审独立复算；没有新增源码缺陷，不再修改、打包或重复审核此候选。

当前INSTALL_ACTION_APPROVAL=NOT_ISSUED，OWNER_ROOT_PIN=NOT_REGISTERED。下一步只请求原独审窗口根据既有ADMISSION协议另作准确版本、限时、单次install动作决定，包含一份源文件原子替换、一次Portal重启及新源/新PID/health通过后的四次空body403检查；不包含回滚、DNS、网站/current或其他服务器变更。全部准确常量及执行/失败边界已保存evidence/pr122-r4-controlled-install/INSTALL_ACTION_REQUEST_20261016.json，显式NOT_APPROVED、时间/nonce为空；不能用作批准。只增加交接材料，不改已批准源码、制品、绑定文件、workflow或生产配置，不重新跑60/18/44/83/45/115。

真正准入需原独审窗口单独签发，并在发布后独立计算原始评论全文SHA，将实际ID/全文摘要由独审渠道交给Owner；随后由可信root登记固定私有锚点。开发方不代签、不创建锚点。现有非rootRunner及旧已消费helper没有新动作登记权限；长期Owner授权有效，但不能虚构技术接入。生产安装/POST/重启/回滚均NOT_EXECUTED；DNS_RELEASE和东京退役继续HOLD。IP审计、外围动态边界和DNS管理面核对未关闭。其他writer的SaaS修改保留，按新HEAD/CAS续接。


### 9.25 2026-10-16：Owner东京root安装成功，启动两地非root公开证据采集

Owner已从原独审窗口独立提供正式动作许可6206046505及完整原始正文SHA2569d08d0b49af0d40ad228928fca87c6d327b3db77b1bceb26daefbb215efb06bb。开发窗口实际读取原评论核对匹配；许可为准确b4b8ed3f/install/1次，2026-10-16北京时间21:37:45到期，不包含回滚、DNS或东京退役。

本次Owner在东京admin/root实际完成私有锚点登记和准确安装器调用，终端返回INSTALL_EXIT=0、LIVE_R4_CONTAINMENT_PASS。工作目录/var/tmp/pr122-r4-approved-29hspn8q；source原d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0→候选57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1，Portal PID3075458→3082952、active/running/admin/既定WD。两地GET200/HEAD501；两地空头及合成不可信头共4次空body POST均403、TLSverified、synthetic_empty_request=true。rollback_started=false、error=null、website_files_changed=false、dns_change=false。此段为Owner实机终端证据，独立实机审核未提前PASS。

复用现有v27只读工作流，移除已完成60模型/打包push job，仅新增两地非root公开证据采集：东京读root0644公开回执、准确源fstat/hash、固定服务状态及Work首页SHA；国内核对current和同一首页SHA。采集器不调用root、不读私有准入/备份/消费目录或凭据，不import生产应用，不发送任何HTTP/POST、不改服务/配置或DNS。它不能将未读私有文件冒充独立核验。旧60/18/44/83/45/115不重跑；已审b4源/原制品不变。最终非root证据以实际Job原始日志为准，尚不预写PASS。

安装后HTTP TikTok断开对所有人（含管理员）暂不可用；完整鉴权仍NOT_IMPLEMENTED。后续只集中验收实际执行回执及既有IP/DNS发布缺口，不扩大源码审核。DNS_RELEASE=HOLD，东京后台与桥接保留，东京退役HOLD。


### 9.26 2026-10-16：R4生产回执与两地Runner原始日志闭环

准确非写采集提交2f644ece195b6001d3dc67cfe135b2b7ee48ea18，Run38836924350：东京Job116768015672与国内Job116768015892均SUCCESS，已分别实际读取PR122_R4_POSTINSTALL_RECEIPT原始日志。东京uid1001、国内uid1002；旧四台dispatch作业SKIPPED。采集器HTTP/POST/服务动作/生产写入均0，不是又一次root部署，也未重跑已通过测试。

东京root0644/nlink1公开回执1689字节，实际SHA2563027b9a01364654aa844f64264cdc0b7506d9c039d45807c3d308d2dfd0fd568，LIVE_R4_CONTAINMENT_PASS且原源/候选/动作/8项check/无回滚均符合Owner终端实际结果。非root另核当前生产源85197字节、uid1000/gid1000/0755，SHA25657e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1；当前服务与root回执after一致：PID3082952 active/running/admin/WD=/opt/trading-system。读不到root私有锚点/消费标记/源备份，不冒充直接独立读取这些文件。根动作实际执行渠道是Owner现有admin/root，非rootCI仅交叉核验公开证据。

两地首页11461字节、SHA2564cdaa871b46fb8f62a5527a81724a9a955beed76542dba922bb4ac9779e90f20一致，国内current仍/var/www/wenwenwenyiyiyi.work/releases/pr122-d8b08ed-recovery-stage。root安装记录两地GET200/HEAD501、共4次空body负向POST403/TLSverified；这里只消费记录，不重新发POST，不读账号/Token状态或DB。完整数据evidence/pr122-r4-controlled-install/LIVE_INSTALL_AND_RUNNER_EVIDENCE_20261016.json。

R4临时遏制实际执行成功且得到两地非root证据支持，集中请求原独审窗口仅确认本次实机安装/限定403结果；不再重审未变源码、归档或60项模型。完整断开鉴权NOT_IMPLEMENTED，HTTP功能对所有人暂不可用；其余业务写路径未测试不写PASS。W06仍部分完成；IP审计差异/外围依赖及DNS管理面核对独立保留，W07/DNS_RELEASE=HOLD。网站入口及整体服务器迁移尚未完成，东京后台和隧道保留，东京退役HOLD。


### 9.27 2026-10-16：R4实机验收关闭，仅收敛IP与DNS管理面

实际读取独审6206210165：LIVE_R4_CONTAINMENT=PASS_WITH_SCOPE_LIMITS；本批R4实际安装及限定四次403验收关闭，禁止重复安装/重启/POST和既有测试。W06仍只剩原有IP/外围动态边界，DNS保持HOLD。服务器完整迁移及东京退役不因网站入口验收推进而完成。

本次只复用旧Job116566967626和116626465013原始日志、已批准312efdd3的tokyo-nginx-source-inventory及代理配置，未重跑服务器探针。另在本地对准确D5源与批准57候选作纯字节/AST对照：R4分支替换不改变log_message、_origin或imports结构；候选摘要与生产已验57一致。未import生产应用或执行测试/网络/业务数据读取。

重要语义澄清：东京Nginx11项动态职责的既有proxy_pass均指127.0.0.1:18080。配置与TCP语义推导下，Portal.client_address是这段loopback连接的对端，并不是HTTP X-Real-IP；迁移后变化的是东京Nginx.remote_addr及其覆盖的X-Real-IP，不能把两层都笼统写成“后台看到国内地址”。此为配置推导，不冒充新的实机抓包。原83模块证据仅观察到日志/Origin和session/form计数，未证明未知云WAF/日志封禁消费方无IP依赖。Owner仍未明确接受临时审计差异，开发方不代为接受。

集中边界/回滚材料evidence/pr122-r4-controlled-install/REMAINING_IP_DNS_DECISION_20261016.json：请求只裁定本次临时入口的具体IP差异及实际受影响的外围策略，不扩大回头审未变源码。Cloudflare原12条导出、proxied:false/TTL字段1及权威A47.245.53.152/TTL300、AAAA权威NODATA继续按历史证据复用；不重索全区导出。真正仍缺切换前当前管理面的zone/单条recordID、A/AAAA枚举、代理/TTL读回和同记录回退绑定。

已检查当前工具及Cloudflare DNS插件目录检索，没有找到可用DNS管理连接（目录检索非穷尽，未推荐无关插件）。GitHub本身不是Cloudflare账户执行通道；不读取凭据或把公共解析当账户快照。下一接入仅需合法Cloudflare管理面读取权限，当前不修改DNS。DNS_RELEASE=HOLD；官网/current、生产配置、桥接/隧道和所有服务本轮未改。


### 9.28 2026-10-16：Owner报告已保存主域A，进入单次非写观察

Owner通过自己的Cloudflare管理面报告已保存；编辑截图显示完整apex名称，保存后记录列表截图image(20261016-021723).png显示A/47.101.152.210/仅DNS/TTL自动。这里只确认Owner操作与可见字段，不把截图当公网传播、AAAA枚举或准确recordID证明；旧47.245.53.152仅按既有历史证据保留。开发窗口未修改DNS，也未代签既有IP差异及DNS发布许可。正式DNS_RELEASE仍未获批准；如当前已生效，应按实际已发生的Owner变更记录，不改写为预先批准或迁移全部完成。

原v27同一concurrency队列准备一次国内/东京非root观察，仅公共A/AAAA/DNS答复、主域和国内固定IP的TLS校验GET首页、主域只读healthz GET、HTTP根重定向及本机已批准Work首页/current哈希。禁止OAuth路径、POST、读取凭据/数据库、root调用、源码/配置/服务/DNS变更、自动回滚或重试。原R4公开回执采集限定原执行提交，避免重新采集已通过安装；tokyo旧dispatch作业保留。不是重新审核源码/旧制品/静态115，结果以新job原始PR122_DNS_POSTSAVE_RECEIPT为准。


### 9.29 2026-10-16 10:19 CST：主域实际已到国内，两地单次非写观察通过

准确观察提交fe9e1320bd9a9602b061b1e7c0e8dce5aaac95cc，原队列Run38839813239：国内Job116777069808、东京Job116777069985均SUCCESS，已消费两条原始PR122_DNS_POSTSAVE_RECEIPT。两台Cloudflare权威NS从两个实机视角均返回AA/NOERROR/A47.101.152.210/TTL300；AAAA均AA/NOERROR/ANSWER0+SOA（serial2417602619）。两机系统resolver均为国内A，主域真实TLS连接peer均47.101.152.210，证书验证成功；首页200/CSP存在/11461字节/SHA4cdaa871…90f20原值。固定国内IP同样匹配；主域healthz GET200、HTTP根308至同域HTTPS。国内current及两地本机Work首页哈希保持原值。旧R4/UK/Korea/dispatch作业SKIPPED，没有重做已通过部署/测试。

实际网站主域入口切换已发生且上述技术链路PASS；不再将这几项写成“尚未验证”。但IP审计限定范围决定和正式发布收尾仍未取得，不把事实观察冒充先前独审放行或完整服务器迁移完成。精确账户recordID/切换前snapshot没有取得，当前截图支持A/仅DNS/自动，AAAA权威无记录支持当前服务事实而非账户全枚举；回退目标沿用历史47.245.53.152、同主域A/仅DNS/自动，不执行回退。完整收据evidence/pr122-r4-controlled-install/DNS_POSTSAVE_LIVE_EVIDENCE_20261016.json。

采集器非root，仅上述固定GET/公开DNS/首页哈希；POST、OAuth、业务数据/凭据/root/服务/生产写入全部0。观察job限定准确本次commit，后续提交不自动重复。请求原独审只核本次新现场结果、当前截图/AAAA与回退证据是否足够，以及既有IP材料的剩余限定决定；不重新开发或重审官网/HTTPS/OAuth/R4/原制品。东京后台、隧道、Telegram/Finance保留，S01–S12完整迁移和东京退役未完成。


### 9.30 2026-10-16：独审6206608746关闭主域实际切换验收，转入有界IP/后台依赖收尾

已从GitHub原始回执读取DECISION=DNS_CUTOVER_OBSERVED_PASS_WITH_SCOPE_LIMITS；主域入口/HTTPS/静态与health正式增量验收通过。W08已完成，W09的两地公共解析/TLS/首页/health/308及内容保护已通过；W06/W07剩余IP审计裁定、W09观察范围及W10收尾未整体关闭。W01—W05与日志/R4等已过范围全部继承，不重审、不重复运行。POST_CUTOVER_RELEASE_REVIEW=PENDING与已经切换的DNS事实分开；下一动作不得再次修改或回退DNS。

当前仅补两机可见的来源IP外围依赖：同一v27队列、非root、固定systemctl列表/只读show元数据、ps仅comm和固定安全工具目录lstat；不读取ExecStart/Environment、服务配置内容、原始日志、凭据、DB、firewall或云策略，不HTTP/POST、不服务操作。仅以命名范围给出可见安全/日志代理存在性与状态；未知自定义/远端消费方和云策略不能推断不存在。原83本地源码及Nginx/Portal IP路径证据不重做。若发现明确服务依赖则集中列最小核验；无论结果如何，Owner尚未接受的审计差异不由开发方代签。

S01/S02继续沿原共享依赖账本整理现有实际消费者/目标与阻塞，PR99/Finance/英国P2/隧道/WeCom实际迁移本轮不操作。S05保护状态兼容与托管仍NOT_IMPLEMENTED/NOT_RUN，已审SQLite候选不是旧Portal的即插即用替代，不能为“迁完服务器”直接复制启动。东京18080、Telegram、Finance及隧道继续在线，退役HOLD。


### 9.31 2026-10-16 10:26 CST：外围IP元数据补证完成，剩余策略缺口具体化

准确探针de30ac366cd907e6b8337c4c7eba74d146254e8d；原v27队列Run38840397178，东京Job116778914578、国内Job116778914372均SUCCESS，已读原始PR122_IP_PERIPHERAL_RECEIPT。仅非root systemctl元数据、ps comm和9个固定路径lstat，配置/原始日志/凭据/业务数据/HTTP/POST/root/生产写入全部0；旧R4、DNS观察、四机dispatch全部SKIPPED。本次探针限定本次精确提交，后续不重复。

两机命名范围没有观察到fail2ban/crowdsec/modsecurity等列举工具的unit或固定目录，但不能扩成全机没有封禁。两机aliyun.service为active/running且存在AliYunDun/Monitor/Update进程；aegis.service虽inactive/PID0，不能据此称安全代理停止。两机auditd/rsyslog均active。此为存在性事实，不是新增源码缺陷，也不说明这些代理实际按IP封禁；对应云策略、rsyslog/远端消费规则尚未读到。缺口从笼统外围UNKNOWN收敛到已命名服务和适用策略，非root元数据不能签该策略的放行。

集中证据evidence/pr122-r4-controlled-install/IP_PERIPHERAL_METADATA_AND_REMAINING_GATE_20261016.json。继续复用83源/Nginx链路；请原独审只判定本次限定范围和明确所需的具体策略证据，不重开网站/HTTPS/R4/OAuth/旧制品。Owner对Tokyo peer/header审计差异的接受仍未给出，开发方不代签；更不能用审计接受替代未知安全规则验收。当前不操作DNS、不修改代理头或信任配置、不停安全代理、不重启任何后台。
