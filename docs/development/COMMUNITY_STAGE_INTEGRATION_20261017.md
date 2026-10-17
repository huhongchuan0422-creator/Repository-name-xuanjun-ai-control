# 社区分账第一、二阶段集成开发记录

## 执行与审核边界

2026-10-17 Owner再次明确：必须阶段性完成后集中审核，不进行断点审核。
沿用Issue76和ChatGPT原隔离分支。此前#6229454350小批送审不能视为阶段完成，本轮不追加小批审核请求。
PR118准确基线71024b22f0d6110f0507dbd8476468313f8846f2；PR122准确基线ffebd6254c0116ae8023efcc2ae714fc5a275560。
在ChatGPT原分支吸收原PR122基线；不修改PR118/PR122分支引用，不启动对方工作区writer。旧模块保留准确原始字节，新接线仅新增独立路径。governance/features.json只追加既有SAAS_AI_PRICING登记。

## 本批实际代码

- community_stage_runtime.py：原Phase1 DemoService和Phase2 OfflineSaas统一dispatch；Principal及门店绑定从服务端配置取得，客户端不能指定租户/角色/支付成功；所有广告及报价时间使用服务端时钟。
- community_stage_local.py：复用原orders/merchant/ad/refund/module/SaaS-order数据库格式，持久打开并验证；原组件的独立文件仍保留，不虚称跨库原子事务。私有目录、数据库符号链接拒绝、排他进程锁、失败释放句柄；不自动seed、不迁移生产数据。
- /offline/community-stage：商家展示、小程序流程、H5流程、商家与平台读视图、SaaS目录/订单/恢复共用同一HTTP服务。旧SaaS编辑、审核页面仍在/offline/saas-panel。
- clients/community-mini：真实微信开发者工具项目结构，既有AppID；wx.request对接同一服务的模拟订单与两个广告位。令牌仅内存，不保存密钥，不调用requestPayment。开发配置仅本机HTTP，不是微信发布工程验收。
- 原订单SUCCESS只生成MOCK_PAID_SIMULATED结果；成功广告必须读取原订单持久状态且经过原广告审批/有效期筛选。模拟结算操作仅Python测试操作员hook，禁止HTTP调用。没有真钱效果或Finance入账。

## 40节点追踪

责任：ChatGPT负责本批独立接线；既有模块归属及独审结果不变。以下是源码证据状态，不是审核PASS。

| 节点 | 源码/集成现状 | 测试证据或下一依赖 |
|---|---|---|
|P1-01|服务端Principal绑定既有Tenant/Merchant/Store|runtime跨租户/角色测试；生产Identity仍待接入|
|P1-02|既有商家目录统一HTTP|新增真实Chromium商家读取|
|P1-03|原签名场景与金额校验复用|二维码签名→原订单；实体微信扫码预览待验|
|P1-04|原生小程序工程及请求客户端；国内服务器预览上传成功|Run39006945633、Job117321450248 SUCCESS；真机扫码待验|
|P1-05|OWNER_DEFERRED：公众号暂缓|2026-10-17 Owner明确不作为本轮完成条件|
|P1-06|原持久订单状态机复用|重新打开后原订单/事件保留|
|P1-07|统一loopback HTTP|真实HTTP及Chromium，不公开服务|
|P1-08|原生小程序客户端及H5客户端|金额/旧响应/伪成功拒绝|
|P1-09|原商家编辑/订单/广告复用|服务端角色和门店绑定|
|P1-10|原平台审核/审计复用|商家不可调用平台审核|
|P1-11|前后广告按原订单状态读取|成功/等待/过期/故障降级|
|P1-12|原退款/分账/对账预览复用|101=退款11+分配90；实际结算UNKNOWN|
|P1-13|五视图共用同一订单端到端|新增Chromium测试；非微信设备E2E|
|P1-14|进程锁、重开、权限异常|新持久host与既有恢复回归|
|P1-15|原专用CI执行整阶段回归|Run39006945633成功；后续代码需绑定新CI，不送断点审|
|P2-01|原报价API接入统一HTTP|既有Phase2全量回归|
|P2-02|原SaaS订单API接入统一HTTP|不替代消费者收款订单|
|P2-03|原权益只读API复用|不发放正式权益|
|P2-04|原后台审核API复用|权限/任务状态回归|
|P2-05|既有Center账号、会话、项目权限；新增受保护微信code绑定HTTP|原Center实例组合测试；现场账号/KMS/HTTPS接入待验|
|P2-06|原SaaS市场页面保留|原Chromium市场测试|
|P2-07|原CNY/USD多方案报价复用|既有价格及脱敏回归|
|P2-08|原客户订单中心复用|原浏览器报价→订单测试|
|P2-09|原续费计划及页面复用|真实确认Finance外部依赖|
|P2-10|原Owner定价编辑审批复用|真实Owner认证未验|
|P2-11|原Finance证据需求接口|权威Finance verifier未连接|
|P2-12|支付凭证真实验签|新增原始报文RSA验签与AES-GCM解密源码；真实公钥/公钥ID与绑定待核|
|P2-13|原订单事件/Quote哈希关联复用|真实结算事件外部依赖|
|P2-14|原权益intent保持只读|真实财务确认及grant权限待验|
|P2-15|原退款冲正预审复用|真实退款/冲正保持HOLD|
|P2-16|原精确schema验证复用|旧生产DB迁移源与授权待提供|
|P2-17|原跨库审计复用|没有跨文件原子提交声明|
|P2-18|原WAL/中断恢复+新运行时重开|真实主机故障注入未验|
|P2-19|原并发幂等+本批单进程锁|并发、重复退款与重复事件回归|
|P2-20|原备份复用；新增六业务库维护态快照和新目录恢复|7项真实SQLite检查通过；现有Center备份仍由原系统负责|
|P2-21|原package保留；新增确定性源码ZIP含运行时/页面/小程序/测试和逐文件Manifest|源码包逐字节校验；不构成生产安装包|
|P2-22|原服务端令牌配置复用|本批内存令牌；生产Secrets未接|
|P2-23|原health/rollback_preview复用|真实安装/回滚HOLD|
|P2-24|小程序工程、微信真实预览上传通过|扫码/现场登录待验；公众号OAuth按Owner暂缓|
|P2-25|不调用资金API|服务商认证/真实sub_mchid/产品权限未验|

## 可复现验证

python -B -m unittest discover -s tests -p 'test_community_*.py'
python -B -m unittest discover -s tests -p 'test_stage5_*.py'
node --test clients/community-mini/client.test.cjs demos/community-local-e2e/*.test.mjs demos/community-payment/demo.test.mjs demos/community-admin/admin.test.mjs

Playwright固定1.55.0并安装Chromium；缺少浏览器不允许标完整PASS。精确版本与GitHub实际CI回执在Issue76记录。

## 尚不能关闭的阶段门禁

PHASE1_FULL_ACCEPTANCE=NO；PHASE2_FULL_ACCEPTANCE=NO。微信开发者工具实际编译、上传与预览并没有执行；真实Identity实现和现场验证尚未取得，不得把浏览器模拟当成小程序验收。真实Identity、微信服务商验签与Finance接线、旧生产DB迁移及生产安装包仍缺。独立审核只在完整阶段候选和全部证据齐备后集中提出。本批不是完整阶段交付，也不是新的审核申请。

新增community_stage_package.py生成确定性离线源码ZIP，原生工程/全部community与stage5源码和测试/页面纳入Manifest逐文件SHA256；明确不可安装、资金与部署HOLD。归档不包含环境凭据、数据库或证书。

## 服务商验签离线实现

community_wechat_sp_verification.py对原始响应/通知字节进行RSA-SHA256验签，绑定配置的PUB_KEY_ID与300秒窗口，再AES-256-GCM解密。严格匹配服务端特约商户、服务商、小程序、订单号、CNY整数分金额。11项测试使用现场生成的合成RSA密钥，不读取GitHub Secrets或真实商户材料。重复通知仅返回候选摘要，不能据此授权重复处理；必须复用原有持久订单事件去重与查单对账，不另建回调队列。函数未暴露HTTP，不写Finance，不将密码学通过当结算通过。

协议来源：https://pay.wechatpay.cn/doc/v3/partner/4019605946 与 https://pay.wechatpay.cn/doc/v3/partner/4012081673 。新增验证依赖cryptography==50.0.2，CI Python3.12；英国现有Python3.6.8不能据此视为依赖兼容已验收，目标独立容器运行时仍需发布前验证。真实响应/回调验签、商户证书配对及查单均未执行。

## 2026-10-17 12:30后继续开发（仍不送断点审）

Owner确认小程序和微信支付服务商已经接入，沿用既有配置；公众号暂缓，P1-05正式记OWNER_DEFERRED，不阻塞本轮。公众号源码保留，测试保留作回归，不计本轮上线门禁。

新增community_mini_login.py实际实现code2session固定HTTPS传输、禁止重定向、超时、敏感URL异常清理；只在服务端使用AppSecret，丢弃session_key，不向小程序返回openid或提供商密钥。MiniGateway要求复用现有IdentityPort：原子reserve_code先于提供商IO、结果未知时code不可重用、只绑定既有客户、每次业务请求重查会话撤销/过期和服务端scene门店权限；不自建用户表或会话数据库。当前仓库尚无可直接调用的生产Identity消费端，测试使用明确的FixtureIdentity，不能宣称已连上生产Identity。

community_mini_http.py新增本机login/api/logout运输；严格Host/Origin/重复头/正文长度/绝对超时/重复JSON和非有限数拒绝，非生产HTTPS listener。原生session.js接入wx.login→code-only后端交换→内存令牌→scene业务请求→退出；scene最长32字符且禁止查询/路径注入。原本离线模式保留，绝不在真实登录失败后降级成离线登录。新增真实HTTP组合测试复用原StageRuntime与原orders SQLite，提供商与Identity仍为明确夹具。

新增community_mini_preview.cjs和专用CI job，使用现有小程序上传Secrets与官方miniprogram-ci@2.1.31，只请求开发预览，不提交公众审核、不发布、不操作服务器或资金。只有提交信息包含[mini-preview]才启动；先通过全量测试。SDK安装步骤不接收凭据；实际预览步骤屏蔽SDK自由日志，仅输出固定状态码，并上传绑定HEAD/小程序源码哈希的脱敏回执。此机制本身不是上传成功证明，须读取实际CI及回执。

本轮真实预览尝试Run39003094810：完整源码测试job117309948995通过，但预览job117310203788失败。实际下载Artifact12089912921（外层ZIP731 bytes，SHA2561377db5ca2147c6b233e19192fabe98105c6ee2611370c15b07bd81019c54c7f）并读取receipt.json，准确状态UPLOAD_KEY_PARSE_FAILED，未到微信上传端，不能描述为白名单拒绝或上传成功。继续对现有Secret支持JSON引号/转义换行的安全格式归一化，不输出密钥，不重复创建Secrets；后续回执为准。

补齐community_wechat_sp_readonly.py：仅允许固定微信服务商商户订单GET，商户/特约商户/小程序/订单号/金额全部要求服务端绑定；请求RSA签名，响应公钥验签并核对金额与商户，失败UNKNOWN且不重试。不包含真实支付、退款或分账调用。增加本地证书/私钥/序列号配对验证；7项合成密钥/签名响应测试，不等于真实商户认证通过。

补齐消费者订单归属校验：MiniGateway创建订单前必须由既有Identity/CRM原子保留customer-order归属，失败/未知不释放；读取收据前必须重查当前客户归属。禁止凭同租户同门店就查看他人收据；原orders数据库不新增重复表。IdentityPort生产实现必须验证历史订单也不能被重新认领。新增同门店第二客户读取/抢占拒绝HTTP测试。生产IdentityPort仍待现有系统实际实现，不用测试Fixture冒充。

持久模拟站点可直接运行：`python -m scripts.community_stage_local --state-directory /private/test-state --policy /private/local-policy.json --port 18795`。policy文件必须进程Owner所有、0600、非链接，结构为`{"principals":[{"token":"本地测试能力令牌，至少32字符","role":"CUSTOMER或MERCHANT_ADMIN或PLATFORM_OWNER","tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}]}`；不包含微信凭据。不自动插入商家/订单；商家资料经既有本地编辑端点写入。该运行入口只绑定127.0.0.1，不是生产部署。

原生小程序新增显式恢复查询：重开页面后凭订单编号只查询既有订单，由Identity客户归属门禁控制，不会重新下单或触发资金操作。回填服务端原金额；同一已创建订单的金额快照变更被拒绝。该路径补齐客户端中断恢复，不代替生产Identity实现。

第二次预览Run39003355408/job117310920432原始日志明确UPLOAD_KEY_NOT_PEM：既有Secret存在，但其值不是可解析的PEM；JSON引号/转义换行兼容后仍未到微信上传端。追加仅在确认为RSA私钥时接受base64编码的PEM/DER；对应测试确认归一化前后公钥相同，不改变密钥、不打印原文。若仍非私钥将停止该错误路径，不用假密钥或自动改写Secret。

## 现有客户中心真实源码复用接线（本轮后续进展，取代此前“未找到实现”的依赖判断）

在既有Work分支feature/work-pr122-site-hub-integration-20261016中定位实际客户中心源码。精确来源bc9404216f2eb69dabf7754950a966238e758596的scripts/pr122_customer_core.py原始SHA256=f9a736fa954bcc3fbdf2eea317bb0b71559864126c940ac6738a4bc9e4a87bd4；本分支逐字节复用该文件，未修改上游/Work分支和该文件字节，来源锁文件COMMUNITY_PINNED_DEPENDENCIES_20261017.json纳入源码包。不能以“旧模块在别处分支中”直接判断实现不存在。

新增community_mini_center_identity.py真正实现IdentityPort，使用原Center数据库的accounts/sessions/links/events/audit/project/members，不新建任何表或用户数据库。mini session使用原sessions散列令牌、epoch和有效期；每次请求重查原项目成员角色、租户及当前provider绑定。原网页退出、项目撤权、微信解绑立即使mini访问失效；仅既有已验证账户可绑定，不创建管理员或新用户。protected Python绑定入口只接受既有网页会话和经可信微信交换取得的subject，不存在公开自报openid绑定接口。

登录code先在原events原子消费，成功session/metadata在同一Center事务内写入；未知/失败消费记录跨重启保留。订单归属在原links加独立命名空间保留，原orders仍是唯一业务订单；创建前拒绝重用/历史未归属订单，收据比较真实uid、项目和原金额。Center事务与订单SQLite不是跨库原子事务，保留未知reservation并拒绝盲目重发，不假装已解决跨库金融提交。

12项新增组合测试真正调用原账户注册/验证/登录、签名项目准入、原SQLite会话/权限/审计和持久重开，验证同门店第二客户拒绝、原退出/解绑/成员撤销立即生效、code和未知订单reservation持久。账号/邮箱、邮件送达、CRM签名和微信交换仍使用明确合成数据；这是实SQLite/原源码集成，不是生产用户或微信设备验收。

第三次开发预览Run39003533437/job117311443454仍为UPLOAD_KEY_NOT_PEM（2026-10-17 12:43:38北京时间）。已覆盖标准PEM、JSON引号、转义换行、base64 PEM和有效RSA DER；现有GitHub Secret没有成为可解析的RSA上传私钥。停止自动重复此路径，不使用假key，不覆盖Secret；已有AppID/服务商配置保留。完整代码回归与原生预览失败分别登记，不合并为PASS，不送审。


## 2026-10-17 国内固定出口上传调整

Owner要求通过已有服务器执行小程序预览。mini-preview改用已有xuanjun-domestic-ops Runner，加载凭据前核对主机iZvt5t8tlrm8oiZ、账号githubrunner且非root。保留既有代码上传IP白名单；未更换私钥。此次调整仅涉及预览任务执行位置，不安装或启动网站服务。旧云端预览Run39003533437仍在途，新服务器上传尚未启动；需要旧任务终态后再触发带[mini-preview]标记的提交。Runner在线、Node兼容性、实际公网出口及微信接收结果均待实测，不能记为已通过。

国内实测Run39006124038：源码测试成功，主机及githubrunner非root校验成功，checkout成功；setup-node步骤持续无终态，微信上传尚未开始。替代路径准备：云端无凭据安装固定版本SDK并打包带SHA256的临时制品，国内Runner使用自带Node20执行，仅在原预览步骤读取上传Secret。不更改系统Node、不使用root、不更改现有服务。新路径运行结果待实测。


## 2026-10-17 继续完成阶段调用链（以本节覆盖前述旧状态）

- 微信代码上传已真实验证成功：HEAD0a12a197e8edd0c3bd3b2036d913da116ccbee2d，Run39006945633，微信回执DEVELOPMENT_PREVIEW_UPLOADED；不再列为阻塞。源码测试/SDK制品/国内预览三个job均成功。记录见Issue76评论6230293495。未关闭白名单，未更换私钥。
- 新增community_mini_application.MiniApplication组合入口：注入既有Center实例/KMS与服务端门店和场景映射，复用原六库运行时、现有CenterIdentity和真实code2session客户端，仅监听loopback，Center生命周期由原宿主负责。无新增账号库、种子账户或自动导入客户权限。
- /mini/bind仅接受一次性微信code；X-Center-Session和X-Center-CSRF必须通过原Center会话、CSRF、维护状态及原持久限流。外部交换前持久消费code，返回后复查会话，拒绝另一账号抢占微信身份。响应不包含openid、AppSecret、微信session_key或Center凭据；超时保留消耗状态。该入口供既有Center受保护适配层调用，尚未接入现场网页路由。
- 新增9项真实Center SQLite及HTTP组合检查，涵盖绑定后同账号登录、CSRF/匿名拒绝、撤销竞态、身份抢占、限流、失败重启、组合入口重开及原Center生命周期。微信网络为合成fixture，不能称真实用户登录通过。

完整阶段仍需的外部条件一次列明：既有Center现场实例与KMS接线、有效客户/项目/门店授权、已部署且登记的小程序HTTPS后端域名及微信真机login code、合法sub_mchid与可信微信支付公钥/公钥ID、权威Finance消费接口与真实对账证据、生产DB迁移基线和安装/回滚准入。没有可用的现有Finance服务实现，禁止新建第二套账本补空缺，也禁止凭支付通知候选或测试HMAC发放正式权益。生产安装和真实资金保持原门禁。Owner要求完成两阶段后统一独审，当前不发断点审核申请。

六库恢复组合已补齐community_stage_recovery：仅允许既有Center维护态、未启动listener、无未提交业务事务时生成六库SQLite快照；独立保留Manifest SHA256；恢复先验证全部文件并检查SQLite完整性/外键，仅创建新目录，不覆盖既有路径。拒绝符号链接和硬链接；故障仅清理本次新建目录。不宣称跨库ACID，Center本身沿用原负责人备份。7项专项测试成功。完整本地回归：249项community Python、342项stage5 Python、72项JS全部成功，共663次测试执行，非独立审核/生产验收。


## 2026-10-17 持续补齐真实边界的源码接线

- 重新核对原PR122至评论6230405005：客户中心仍未生产安装；公共HTTPS/KMS/真实CRM授权未交付。主分支完整树及finance分支检索未找到权威Finance服务实现。只记录当前可见证据，不据此改写其他部署者状态或重造账本。
- community_saas_provider_evidence.SaasProviderEvidence：仅原StageRuntime注册的PLATFORM_OWNER可接收；服务端冻结订单映射指定tenant/order/cycle/out_trade_no。金额与币种来自原不可变报价，拒绝USD、未知周期及同一支付单绑定两份订单；原始签名通知RSA验签和AES-GCM解密后进入原saas_review_tasks的FINANCE_EVIDENCE。BEGIN IMMEDIATE锁定原库，事件ID、正文SHA、报价claim及绑定hash消除并发重复并拒绝碰撞。重复/重启不重开已关闭审核，不变更订单资金状态、余额或权益，仍需原Finance独立查单/对账。9项专项测试通过，网络及密钥使用合成fixture。
- MiniApplication.listen_proxy：新增Unix后端入口，复用原pr122_customer_source.TrustedNginxSource的Linux SO_PEERCRED固定Nginx UID与单个来源IP校验。该模块从原b882ea631e6391f1fc8727766ccbaf3c66b519da逐字节复用，SHA256=3e8d531ede69577b72b6ee9089fdc8f481b2f91578f19e0e44d1841c168f3471，纳入依赖锁及源码包；不修改原writer源码。HTTPS Origin/Host固定于宿主配置，拒绝重复Origin；来源登录限流共用原Center auth-source计数。socket目录须既存且受保护，拒绝覆盖，close只移除本实例inode。未创建Nginx路由、运行目录或生产服务。
- 修复真实换码耗时跨秒时沿用旧clock签发会话的问题：provider返回后重新取服务端时间，失败记录也用当前时钟。新增延迟3秒换码检查。
- 本地8项Unix测试因环境禁止创建AF_UNIX socket返回EPERM，未记PASS、不跳过、不绕过。提交到Hosted完整CI实测，成功与否以准确提交终态为准。绑定、网络与身份仍为合成客户/微信fixture，不是生产客户登录验收。


### 持续接线与国内非root验证准备

准确源码d94b5f7288a29dc1f415522a3cc18c4a33822c0c已取得Hosted Run39008839520 / Job117326787519 SUCCESS：267项community Python、342项stage5 Python和72项JS，共681次测试执行，零失败/跳过。8项Unix测试真实执行成功（其中成功身份为显式source fixture；真实不匹配SO_PEERCRED拒绝已验），本地EPERM不再阻塞Hosted验证。

新增community_provider_notification_http：HTTPS/可信Unix代理后方的原始报文入口，仅识别服务端发票映射生成的固定回调路径；不接收客户自报order/tenant/verified。拒绝重复请求头、Origin、重定向路径、无签名/错金额；正文限1MiB、读取deadline1秒、SQLite锁等待1秒；只有原FINANCE_EVIDENCE持久提交后应答204，失败/未知不应答成功，不产生真实付款/退款/分账或权益。7项实际HTTP+合成签名测试通过。官方来源：https://pay.wechatpay.cn/doc/v3/partner/4012085146（普通支付/小程序支付服务商通知）。

新增Unix正向实际peer检查：Hosted/国内非root测试以当前测试UID作为代理fixture，不改SO_PEERCRED函数；只证明隔离边界与应用组合，不当生产Nginx真实登记。

复用原pr122_customer_runtime.py（b882ea631e6391f1fc8727766ccbaf3c66b519da逐字节，SHA256 3a483ed81eb595309665c3d2b5746e56a50016fb246617000eb326dc5ff2b959）；沿用其已固定3个wheel：cryptography46.0.3、cffi2.0.0、pycparser2.23和各原SHA256。新增[mini-runtime]受控触发的Hosted离线依赖打包及国内Runner非root临时兼容性测试；不覆盖原安装器，不Root、不全局pip、不服务安装。主CI仍使用原cryptography50.0.2/Python3.12；国内是原Python3.11兼容性证据，两者分别记录，不混称生产Runtime准入。新任务终态待取证。


### 角色分工及源码制品传递修复

新增服务端注册STORE_STAFF、PLATFORM_REVIEWER、FINANCE_APPROVER：员工仅绑定门店订单/汇总；审核员可广告审核但不能编辑商家或访问财务；财务角色仅读取原退款/分账/对账预览，不能记录退款或执行资金。社区角色不继承SaaS客户/Owner接口权限，客户端不能提交role或复制Principal冒充注册对象。6项专项检查通过。以上仍为受控服务端角色投影，现场账号授权必须来自原Identity/CRM，未开客户端角色选择入口。

8c9b3f9e3108ed870b2285fb625079b1813d47e8的Hosted完整回归已通过；国内Run39009126611仍在checkout阶段，尚未开始应用测试，不记实机PASS。为避免重复依赖国内git下载，替代任务直接下载同Run完整CI产生的源码制品，使用needs.test输出的独立源码ZIP SHA256及Manifest逐文件验证、拒绝重复/非普通文件/路径穿越/过大闭包，再在新RUNNER_TEMP目录运行。原pin的三个wheel继续独立核验，未绕过校验或改为公网pip安装。等待旧任务上传/应用执行终态后再触发新任务，避免并行host writer。

宿主集成所需公开契约：MiniApplication由既有Center宿主注入原Center实例及受保护场景/门店映射，listen_proxy使用现有Nginx Unix peer身份和已准入HTTPS域名；/mini/login、/mini/api、/mini/logout、/mini/bind保留原请求字段与会话/CSRF保护。签名SaaS通知通过SaasProviderEvidence与notification_path/make_handler进入原FINANCE_EVIDENCE，不调用独立Finance余额写入。该Python实例组合不是跨主机Identity RPC的替代；若最终项目容器与Center分离，必须由原客户中心提供受保护的统一服务接口后实现IdentityPort，不能挂载/复制原账号库来假装接通。
