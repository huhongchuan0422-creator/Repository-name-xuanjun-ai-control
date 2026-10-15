# 玄钧云汇自有域名、DNS、官网迁移与可视化交付权威规划 V1.0
**日期：2026-10-15｜工作锚点：Stage5 Issue #76、Draft PR #122｜原审核冻结基线：PR #118 HEAD `71024b22f0d6110f0507dbd8476468313f8846f2`**

> 当前执行状态以第9节（2026-10-15 23:44 Asia/Shanghai）为准。第0—7节含早期采集阶段的历史UNKNOWN，不能据此要求重复导出DNS或重做静态RG1。

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
