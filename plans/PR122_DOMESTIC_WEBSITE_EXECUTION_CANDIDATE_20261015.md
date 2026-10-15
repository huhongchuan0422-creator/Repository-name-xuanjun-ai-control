# PR122 国内官网迁移执行候选 V1（2026-10-15）
状态：PLAN_CANDIDATE / PRODUCTION_HOLD。只记录设计和验收，不包含已获生产授权的安装命令。
归属：原PR122；复用现有SAAS_AI_PRICING关联的第一方预览能力，不新增功能实现或平行任务。权威设计为开发文档8.2.3—8.2.8；顺序沿用主迁移规划D0—D6。本文件不能覆盖主规划或正式Release Gate。
源码基础0997799fdce2dc5de7e0a117080ea838d7e915cb；PR118冻结基础71024b22f0d6110f0507dbd8476468313f8846f2。版本变化须重新绑定受影响制品，不自动继承旧制品哈希。

## 1 已有证据与边界
- #6184353359：主域官网/中英文，sitemap109/109 GET200；visual两个路径404。HTTP200不是业务交互验收。
- #6184420192：Owner DNS导出12条；原文件SHA256 531bc71f3d5eff6cb7ad5c7e6aea3912578a8a91ff8ade740ef2e40d2e7eb771。
- #6184521353：OpenClaw现场回执，东京root /var/www/wenwenwenyiyiyi.work，1187文件11090003bytes，文件清单hash c389d49d362eb45173b576a094c7e5f46b0ad10ec0b172c9a50c361f1dd99474。
- 东京TLS终止及静态文件已定位；国内仅现有winctl/IP站；UK SSH身份被拒。
- Work已读公开回执，未独立取得/核验私有归档；不能将源码方案或摘要提升为实机部署PASS。
- #6184594858与#6184612287为现有协调规划，本文件把候选路径和验收固化，不重复全量采集。

## 2 目标目录与职责（拟议，未创建）
优先让现场执行者确认既有国内release基路径。下面是该基路径下的相对布局，不臆造已存在的绝对路径：
- website/releases/<release_id>/public：官网完整静态树及受审预览资源，运行期只读。
- website/releases/<release_id>/manifest.json：源码commit/tree、原站清单hash、每文件SHA256/长度/模式、路由及依赖版本。
- website/staging/<transaction_id>：仅受控发布身份可写的临时验收区。
- website/current：经验证的release指针；切换方式须匹配现有国内机制，不改其他项目current。
- website/rollback/<transaction_id>：旧指针/原配置hash/权限、安装对象清单、回滚判据，禁止收录明文秘密。
- website/receipts/<transaction_id>：发布、检查及回滚回执，追加记录。
Nginx仅有读取静态release所需权限；发布身份不可任意修改/etc/nginx或systemd。Root变更由正式Gate限定具体文件/命令。若需改现有目录方案，先说明冲突和最小变更。
生产数据、客户上传和秘密引用独立于immutable release。不能全目录打包/opt/trading-system、OpenClaw或共享数据库。

## 3 路由契约与完整迁出账
|路由/域名|现状|候选处理|切换前断言|
|---|---|---|---|
|apex /、/zh-cn/、/en/及深层URL|东京静态站|原结构复制，保留canonical/hreflang/重定向/MIME|109条及非sitemap、资源、重定向逐项验证|
|/visual/|404|复用原PR122统一中心设计，待原开发方交付|导航/版本/演示隔离/手机可用|
|/visual/community-payment/|404|Portal及依赖打包|角色及所有链接/JS/CSS无缺失|
|/community-local-e2e/*|Portal相对链接实际目标|首选保留原目录映射；如隔离新前缀则统一修正并测试|源、目标路由一致，不能仅复制index|
|/customer/projects/<project>/preview/|未验收|服务端可信tenant/customer/project授权|跨租户、失效身份及直接资源访问拒绝|
|主域动态18080对应location|东京secure-secrets相关|只读枚举精确location并区分管理/官网必要/独立业务|保留或迁出责任明确，无意外管理面暴露|
|wecom域18770/18780/18781|东京Nginx反代|独立业务迁移，不随apex自动改A|平台签名/回调/白名单/防重放及数据路由通过|
|/novel/→18761|东京隧道入口|单独列原业务依赖|迁移决策明确，韩国不操作|
|winctl→国内18444|国内生产现站|配置及证书保持|变更前后健康对比|
|center CNAME及验证TXT|ChatGPT自定义域名|全部保留|记录精确不变|
|MX/SPF/DKIM、uk|已导出|全部保留|区域差异仅含批准记录|
API域、cookie/path、反代前缀和CSP最终按已认证API契约确定；禁止把本机演示API或测试token直接反代上公网。保留来源和外部服务责任，不以静态站通过宣布全部业务迁出。

## 4 制品与预览边界
官网源包须来源于现场已核对的实际Webroot及版本，OpenClaw已在#6184795529报告交付1187文件源包，包SHA256为74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63；但当前Work未取得附件字节，因此SOURCE_PACKAGE=REPORTED_DELIVERED、WORK_PACKAGE_BYTES=NOT_RECEIVED、INDEPENDENT_PACKAGE_VERIFICATION=NOT_RUN，不能用公网爬取包代替完整原站制品。
构建前固定文件类型、符号链接及边界；拒绝越出根目录链接和未审secret/DB文件。检测源树漂移后重新固定版本，不悄悄更换manifest。
Portal复用demos/visual/community-payment及community-local-e2e依赖。消费者存在POST；SaaS本机HTTP有Host/Origin限制，不能声称纯静态即可交付完整业务。
公开DEMO只能样例数据；原开发方补社区/分账方独立界面、商家申请/审核/补正/复审、可信反馈持久化。WebAI、Telegram、飞书沿现CRM/CommonBrain身份体系，未连接保持NOT_CONNECTED。真实付款/分账不在此次演示上线授权内。

## 5 证书与DNS方案
国内独立主域SNI，保留winctl/IP原server。证书路径只引用既有受控secret/certificate机制，源站私钥不进入源码或公开制品。
优先复用既有ACME签发/续期；DNS尚指东京时，HTTP-01必须证明挑战能到达实际申请端；如采用DNS-01，精确限定_acme-challenge TXT及清理动作并过写入Gate。不默认已有Cloudflare API token，不为签发将apex提前切换。
签发、证书安装/权限、Nginx修改/reload均属生产动作，当前不执行。国内证书SAN有效、完整链和续期/deploy-hook验收后才具备TLS条件。
DNS变更包是现有导出的精确差异，候选仅apex A东京→国内；wecom另批。TTL与DNS-only保持原策略，不能把导出TTL字段1当作公网1秒。验证记录/邮件/center不变。
验证国内源站需携带正确SNI/Host并检查有效证书，不能以-k或IP证书通过替代。

## 6 UK受控发布
UK为既有控制面；原维护方只读确认准确user/已绑定公钥指纹及host-key、Runner身份/准入、制品接收和UK→国内受限传输、激活/回滚权限。
当前UK_AUTH_BLOCKED，不创建key、不修改authorized_keys、不恢复P2已隔离Runner。现有Runner active不证明具有发布权或准入安全。
需要分别证明CAN_STAGE/CAN_VERIFY/CAN_ACTIVATE/CAN_ROLLBACK；正式发布前必须闭合，离线打包/配置草案不等UK。
发布身份仅可接收固定Manifest/hash制品、验证、切换批准release、检查和回滚；不能接受任意shell或任意路径。

## 7 阶段、验收与回滚
|阶段|工作|本阶段成功条件|当前|
|---|---|---|---|
|D0|复用DNS/现场并补UK、精确动态location和目录|证据完整、责任及唯一写入方明确|PARTIAL|
|D1|源站包+Portal制品+目标配置+命令/权限草案|Manifest、自包含/解压/链接/秘密检查、回滚包校验|待原始源包|
|D2|国内隔离部署/目标Host预检|有效TLS、完整路由/API、资源、身份、winctl不受影响|需Release Gate，不执行|
|D3|集中独立审核及Owner精确批准|commit/tree/artifact/目标状态/范围一致|HOLD|
|D4|受控激活及单独DNS差异切换|发布回执、健康、区域差异符合批准|HOLD|
|D5|跨网络PC/手机/角色/反馈/运维验收|真实证据、监控及回滚通过|NOT_RUN|
|D6|东京全部业务退役验收|含PR99等跨任务依赖闭合、观察及另行批准|HOLD|
每阶段记录开始、完成、失败、超时、部分成功、未知、重启状态。任何结果未知停止后续写动作，保留事务和私有日志；不得盲重试或用再次运行覆盖原回执。
发布前固定目标原状态（目录不存在也记ABSENT），无权限/无空间/占用冲突/锁未得均不进入激活。实际安装命令须依据现场路径和精确artifact生成，当前不提供占位可执行命令。
静态失败回滚只恢复此次指针/新增配置及权限，并重验原官网与winctl；已有目标对象必须用事务身份/原hash绑定，不能rm-rf整个站点。
动态回滚须先阻止新端写入，确认在途请求/外部回执与数据权威，禁止DNS回切造成双写。跨DNS缓存期间旧站保留可用；回滚不能只以进程running为成功。
TLS、Nginx语法或健康检查失败：不切DNS；切后异常：按批准差异回原A，保留国内现场并复验两端。DNS传播不保证即时，窗口和观察期由精确发布包提出后批准。
证书续期/备份恢复/监控及109 URL通过仅是验收项之一；支付、CRM真实写入与东京退役仍各有独立Gate。

## 8 一次补齐材料及当前结论
现场执行方：提供现有Webroot的脱敏可迁移原始文件包/Manifest、动态location分类、国内准确基路径与Root允许动作、UK权限回执；复用已取得证据，避免全量重采。
原开发方：提供所负责功能commit/依赖/受控API/角色和反馈验收证据。Work：核对组合包、候选配置/路径、发布及回滚契约，统一写回PR122。Dots监督不替代实际执行。Owner仅在确实缺账号验证或正式发布批准时配合。
已读main现行Feature Compliance规则。本次仅文档规划，无新增运行代码；不声称新测试或新部署PASS。后续功能改动沿原FEATURE_ID并通过真实CI；独立审核不能由开发方自批。
DNS inventory=PASS；Tokyo topology=reported-pass；UK release=UNKNOWN_AUTH_BLOCKED；artifact=REPORTED_DELIVERED_NOT_INDEPENDENTLY_VERIFIED；domestic apex TLS=HOLD；preview=HOLD；production=HOLD。

## 9 现场输入补齐后的精确落点方案（2026-10-15）
本节补充#6184795529，不重复执行已取得的现场核查。源版本0363531ee2f85ae36093a015c020a7609a65b01f，release xuanjun-yunhui-work-v2-20261013，源1187文件/11090003bytes；报告包7526140bytes，MANIFEST.json hash d9157976ae67e89aba90a8de0d2c606ec62268c6b649d9ebe578f6c2619e0d6a，TSV hash bbb78f9417aac50e5aa07c6469cb559df0693bf3029d3f10a8265758e239bdba。以上是执行者报告，不是Work独立解包结论。

### 9.1 控制目录与公开目录分离
已确认控制基座 /home/openclaw_ops/v8-domestic-operations，home0700、基座/releases/staging0750、runtime/admin_repair0700；不放宽home，不将Nginx或githubrunner加入可遍历home的泛权限组。
候选控制namespace绝对路径 /home/openclaw_ops/v8-domestic-operations/website，供openclaw_ops进行私有制品接收、staging、清单验证、回执和控制指针管理；当前namespace不存在。
候选生产静态namespace /var/www/wenwenwenyiyiyi.work，拟含 releases/<release_id>/public 与current。此路径是**未来拟建**，需Root Gate及冲突预检，不等于国内已安装。
root受控发布步骤必须将验证后的公开制品复制到root控制的公开release，重新验证目标字节，再切公开current；Nginx不能直接root到私有home。公开目录仅含已批准公开文件，目录权限拟0755/文件0644，目标对象及所有父路径root管理，禁止非授权用户替换。
复制不能信任用户可变staging路径：执行时固定输入对象/描述符或root私有接收副本，验证manifest、文件类型/路径边界、数量/大小/hash和复制后结果；reject链接、设备/FIFO、路径穿越及额外文件。源在验证后变动、部分复制或清理失败均保留事务并HOLD。此为执行器要求，当前没有实现或验收其安全性。
openclaw_ops控制指针的成功不等于生产公开指针已激活；发布回执分别记录。root仅操作确切site/transaction/release，不能授予任意sudo或任意路径复制权限。若已有受限执行组件满足要求则复用，不为本任务新建通用执行平台。
Nginx候选配置仅新增主域server，静态root拟 /var/www/wenwenwenyiyiyi.work/current/public；证书路径由已审签发机制提供，不能使用国内IP证书。最终保留原站try_files/重定向语义，不把所有404转首页。由于原始配置尚未在Work侧取得，不生成可直接安装的猜测server block。

### 9.2 动态路由的具体分离
- 公开集成依赖：TikTok OAuth start/callback/status/disconnect、Douyin OAuth callback；路由/平台注册/状态及凭据需分别绑定实际后端。disconnect为有副作用动作，不作为只读验收GET。静态迁移不能让现有已工作入口默默变404或误报NOT_CONNECTED；精确切换方案须明确保留旧后端或先完成迁移，未经证明的临时反代不得放行。
- 受保护管理：/p/、全部/submit/*、/healthz、/telegram-canary/status，不随公开静态包迁出；完整管理路由、权限、凭据提交链及去向未闭合前，不切apex令原管理业务失联。
- 独立业务：/telegram-webhook/、wecom的/wecom/*与/novel/，按签名、网络、数据、消息去重和回滚分别验收；静态包不包含动态服务或客户库。
- Windows Interaction和customer_context.db留在国内原服务，当前不复制/迁移/更改。

### 9.3 尚需交接与授权的真实区别
附件已发送至飞书私聊不等于附件已进入Work会话。Work必须取得原tar.gz字节，先核对包hash再安全检查成员/Manifest及所有文件，不重新要求OpenClaw构建同一包。没有字节时标NOT_RUN，不编造制品验收。
UK仅能确认SSH传输响应与单次PERMISSION_DENIED；命名profile0、未找到当前可调用的批准Runner，不能自动修复认证或安装公钥。优先由既有维护者确认原有准确user/已绑定公钥；如确需修改authorized_keys须另有明确权限修改授权，不能冒充只读步骤。
当前可以继续规划和离线核验，生产目录创建、root复制/切换、TLS签发、nginx-t/reload与DNS仍等待精确Gate；当前不要求Owner提供私钥或密码。
