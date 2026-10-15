# 玄钧云汇自有域名、DNS、官网迁移与可视化交付权威规划 V1.0
**日期：2026-10-15｜工作锚点：Stage5 Issue #76、Draft PR #122｜原审核冻结基线：PR #118 HEAD `71024b22f0d6110f0507dbd8476468313f8846f2`**

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
