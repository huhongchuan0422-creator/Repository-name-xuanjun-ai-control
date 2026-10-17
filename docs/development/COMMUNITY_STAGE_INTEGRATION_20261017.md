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
|P1-04|新增原生小程序工程及请求客户端|6项Node测试；微信上传/预览未验|
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
|P1-15|扩大原专用CI为整阶段回归|精确HEAD CI待终态，不送断点审|
|P2-01|原报价API接入统一HTTP|既有Phase2全量回归|
|P2-02|原SaaS订单API接入统一HTTP|不替代消费者收款订单|
|P2-03|原权益只读API复用|不发放正式权益|
|P2-04|原后台审核API复用|权限/任务状态回归|
|P2-05|统一服务端Principal演示身份|生产登录/真实身份绑定仍缺|
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
|P2-20|原backup/verify_backup复用|原SHA与恢复校验回归|
|P2-21|原package保留；新增确定性源码ZIP含运行时/页面/小程序/测试和逐文件Manifest|源码包逐字节校验；不构成生产安装包|
|P2-22|原服务端令牌配置复用|本批内存令牌；生产Secrets未接|
|P2-23|原health/rollback_preview复用|真实安装/回滚HOLD|
|P2-24|新增小程序工程，H5共用API|微信实际上传、扫码、登录、公众号OAuth未验|
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
