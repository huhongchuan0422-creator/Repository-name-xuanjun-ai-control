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
官网源包须来源于现场已核对的实际Webroot及版本，当前Work未取得1187文件，因此SOURCE_PACKAGE=NOT_RECEIVED、ARCHIVE_SHA256=NOT_AVAILABLE，不能用公网爬取包代替完整原站制品。
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
DNS inventory=PASS；Tokyo topology=reported-pass；UK release=UNKNOWN_AUTH_BLOCKED；artifact=NOT_RECEIVED；domestic apex TLS=HOLD；preview=HOLD；production=HOLD。
