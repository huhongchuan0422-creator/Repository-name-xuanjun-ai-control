# 公共长期接线：可实施候选与一次性认证变更清单

沿78e339db、PR17 #6328988789/#6329032582，不另建任务。本窗口开发，不自签独审。本文件为准入材料，未变更现场。

## 当前源码与完整执行闭包

默认关闭的公共接点之外，已实现第一个真实固定项目动作的源码链：原GitHub receive→Queue.submit/validate→原BEGIN IMMEDIATE/唯一project Writer→execute_ready→WebsiteBaselinePolicy.command→原Cloud RunCommand→原InvokeId记录→query_existing→WebsiteBaselinePolicy.result→PrivateStore→原结果outbox。没有新调度器/DB/任意Shell接口。

固定动作仅website_baseline_collect，固定国内实例，root只读原20项。命令携带完整原采集器，zlib封装在内存展开、核12809字节/SHA后运行，不下载/上传/安装文件。内层25秒/外层30秒、stdout≤32768、命令Base64长度≤16384。压缩不是拆批，原源码字节完全保留。精确采集器SHA c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f。现场未执行；云端输出是否存在服务端截断需实测，不猜值；截断/非JSON/错nonce/主机/InvokeId/SHA均不能SUCCESS，不重复dispatch。

原工具相同20项是观察结果，OBSERVATION_ONLY不代表网站可发布或业务验收。HOLD结果保留原私有失败证据，不只丢弃stdout。scope/标签/数量核对，结果不公开正文。需要可信接收身份后才可向新接收方提供；目前公开MCP仍只有原两工具，不能把内部方法说成外部可调用。

runtime.main现在有正常host配置入口：可选expiry_watch和website_baseline。缺字段不加载、不注册。每项恰为metadata_ref/metadata_sha256；只接受/etc/xuanjun-cloud-executor/tunnel-expiry.json、/etc/xuanjun-cloud-executor/website-baseline-binding.json两固定root受保护文件，核SHA；工具参数不能启用。现有config未改。

本候选完整执行闭包7件（queue.py/worker.py/runtime.py/private_transfer.py/credential_lifecycle.py/fixed_actions.py/pr122_baseline_collector.py）pin：
e672f5f591605b09ad13342dc5a52c11b6fb5679537597fb5e3e24f9daa8839b
私有MCP当前源码SHA（本轮未改）：3c8a94a92b39519bd6797656fed6282815f7fbe0fcd8a794fb0edc77da6e0f86。
旧线上pin/旧安装器不改称本候选；旧enrollment回归使用原三份冻结fixture，逐份核原硬编码SHA。

## 真实身份接口核查与推荐认证改造

已实际打开官方文档：
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels ：Permissions and access、Security and networking、OAuth。隧道是传输；OAuth discovery可经隧道，authorization server不会自动被隧道代理。
- https://developers.openai.com/plugins/build/auth ：OAuth2.1资源服务器逐请求验证access token；requestContext来自服务器处理，不是模型参数。

已核现有private_mcp.py main/handle/stdio：没有HTTP Authorization上下文或逐调用验证主体。params/_meta/clientInfo及隧道workspace关联不作为身份。结论仅限已安装stdio接口及上述文档：未找到可直接消费的逐调用主体；不推断平台所有接口都不存在。不得声称示例loadAuthenticatedProfile是平台现成API。

推荐实施方案（待Owner集中确认，未创建）：
1. 保留现有隧道ID/Read+Use密钥/常驻队列。将同一隧道MCP上游从stdio切换为英国loopback HTTP资源服务，候选127.0.0.1:18769/mcp，端口使用前定向核冲突；无公网MCP监听，不开放任意URL/Shell。唯一连接服务Writer持有原锁，不启动第二worker。
2. 增加标准OAuth2.1授权服务，采用维护中的标准实现，不自研JWT签发器。浏览器授权入口候选https://cloud-auth.wenwenwenyiyiyi.work；这是拟新增域名，不宣称现有DNS/TLS。经批准后只新增此独立DNS/TLS/Nginx入口，不接管官网/社区/客服路由。授权服务放国内固定项目边界，英国资源端只做令牌验证与原操作调用；不同步客户数据库。
3. 授权服务通过项目新GitHub OAuth应用核真实GitHub主体；现有GitHub连接器Token不导出、不复用为MCP Token。只允许332398908（开发收件）和95597695（独立审核收件），root受保护映射绑定recipient及项目，审阅身份不能因此获得开发或安装审批。scope最初仅connection.status/project.files.read；固定动作提交仍沿原GitHub intake及原审批，不给任意写入。App注册/客户端凭据/授权码PKCE/redirect精确白名单/refresh轮换与撤销由标准授权服务处理。
4. 资源端逐请求验issuer、audience/resource、scope、有效期、签名/正常introspection及撤销；主体来自受验证上下文，忽略工具参数及_meta。opaque token或标准签名格式由所选实现决定，不编造平台token字段。token不进聊天、仓库、URL查询、公开日志；新的服务客户端凭据分别root0600/私有secret reference保管。令牌有效期、refresh策略和包版本需在源码候选中冻结后送独审，不能以本文当实现完成。
5. 同一插件正常更新OAuth配置，Owner完成必要的一次安全登录/同意。未获准前不注册OAuth App、不创建凭据、不改隧道profile、不改插件/服务/DNS/TLS。

风险：新增认证服务和公网授权入口有维护成本；错误audience/映射可泄露项目文件，refresh泄漏可形成持续访问，切换可能短时中断旧只读工具。最低验收：缺token/错issuer/audience/scope、过期/撤销、错主体/项目、参数冒充全部拒绝；双主体真实登录与重连主体稳定；日志无token；仅固定清单对象可读；原两只读工具回归。

回退：切回原只读stdio profile和原已核MCP SHA，停新HTTP资源入口、禁用新OAuth客户端并撤销其refresh会话，保留私有日志与原Queue不清库。撤销新增DNS/TLS路由需按原发布机制，不动原业务服务。不得通过回退重放封存请求或扩大旧只读范围。

需一次集中确认的准确变更：新增项目GitHub OAuth应用及专用服务凭据；部署/维护上述标准OAuth2.1服务；新增cloud-auth域名DNS/TLS及独立入口；同一隧道改loopback HTTP上游/插件OAuth配置；root主体→recipient/project白名单；受控凭据私有保管与撤销。均为持久访问/安全设置变更，本文未执行。若已有等价标准IdP实物与准确授权，可先核复用，不能为了省配置伪造身份。

## 到期提醒独立准入（不等待OAuth或项目catalog）

原凭据记录PR17 #6321045032创建于2026-10-21T16:29:37Z，明确平台日期2026-11-20、具体UTC秒未知。候选不把评论创建时间冒充精确现场读取时间；启用前只需原受信平台记录中真实verified_at及generation/source_ref，一次核定非秘密元数据，不创建/轮换密钥。

可实施变更：英国新增版本化release，完整7文件pin如上；原connection.json仅增加expiry_watch，指向上述固定私有metadata并钉SHA；保持website_baseline字段缺省、MCP/profile/roles/allowed_actor_ids不变。原唯一service锁/4 SUCCESS历史不变；核无在途DISPATCHING/UNKNOWN后按原机制切换/restart原唯一服务，回读新版本/原队列、定向验证预警去重与不重放。旧 release/config保留，失败恢复原链接与原配置；不删历史库、通知、InvokeId或key。

影响：保守停止界2026-11-19T00:00Z触发后本循环停止新任务处理并留通知，需在此之前正常续期；通知不能投递则UNKNOWN保留，不承诺后台一定送达。未来换key需新代际准确记录，经正常确认，不重试永久期限或扩大Manage。独立准入只启用expiry_watch，不连带开启网站动作/文件授权。

## 已有项目材料及真实差项（主动核取结果）

|项目|已读权威记录/可复用|实际待补项/责任|
|---|---|---|
|B5|PR17 #6316439576/9ef60498原5份inventory，788可复用；#6316671622补齐12元信息，总372/4114893B；原Manifest cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba|原B5 Writer已#6329086678实际接单冻结selected_members/profile/动态包native资源Node闭包与可信根；非要求Owner找已有Manifest。16MiB预算及Node126595440B不可拆批规避。尚不运输未批准选择|
|官网|PR122 #6319390111品牌496434B/TAR SHA d4b6ae55a6c9c2b88918e1cd4cba2af072dd5cd717efa697b83120bbec3bca46；控制源码106193B/23模块24成员/SHA8eaea6e7acf93cfe25779a6ea91a107b2e653c07f62198eda1d1f964b9c0110f；#6319403826 scope及implementation SHA|公共接线本批已实现固定20项原队列动作。现场准入后才生成真实Invoke/时间/结果。inputs/source根仍无准确引用，范围外服务/Writer/Fence保持另组UNKNOWN；不套旧459Pins|
|社区|Issue76 #6316014038及#6320849617，准确5a5e9369，受保护host config→原MiniApplication已存在，21项Hosted记录；#6320356102已有完整小程序源码ZIP SHA及55项端点证据|客户平台原身份宿主/8类已有store/scene门店与英国实际运行绑定仍由原窗口4核实；不要求PR122/国内CRM作为社区登录前置。预算≤英国1/5且受剩余容量约束，不猜实际字节；普通连接不建空库/账号/真实支付|
|国内客服|在原Issue76 #6313628875/#6313787053读到原国内窗口回交引用：customer-brain-source.json.gz SHA e5047757261a270cd9c5c4a3c8ac50057053bf546143275f713a1bb9eba5a489及既有HMAC bridge契约|本轮检索原PR122最近62条与仓库已连接搜索未定位独立国内客服交付Manifest/原任务ID/当前根与预算；快照是历史结构非当前现场授权。准确原任务引用/固定交付清单待原国内客服Writer登记到原任务，不能说所有材料不存在、不能让Owner搬快照。不得读取客户DB正文/Token或用可建LEAD的round-trip充身份探针|

本轮只读核取记录，不读取受限品牌ZIP、不公开私有现场派生信息或客户资料。已有SHA引用不代表重新独立验包。

## 尚未完成的公共代码与实际验收

已完成候选：官网固定动作真实Queue/worker调用、私有证据保管、独立expiry配置接点。
仍未完成：新的受验证身份HTTP/OAuth资源端、通用项目文件的实际上传/下载工具注册、B5/其他部署动作的准确项目适配（要消费原冻结选择及执行门禁，不能用generic shell替代）、新项目真实双端SHA/跨窗口提交领取/重启与撤销实测。上述包含本连接窗口代码责任，不统称外部缺件。

无线上操作、无新凭据、无OSS、无封存请求重投。源码/Hosted通过不算长期连接完成。原三机/常驻/旧只读收件/续期及重启证据继续继承。
