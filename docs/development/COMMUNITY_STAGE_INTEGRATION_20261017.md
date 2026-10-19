# 社区分账第一、二阶段集成开发记录

## 执行与审核边界

2026-10-17 Owner再次明确：必须阶段性完成后集中审核，不进行断点审核。
沿用Issue76和ChatGPT原隔离分支。此前#6229454350小批送审不能视为阶段完成，本轮不追加小批审核请求。
PR118准确基线71024b22f0d6110f0507dbd8476468313f8846f2；PR122准确基线ffebd6254c0116ae8023efcc2ae714fc5a275560。
在ChatGPT原分支吸收原PR122基线；不修改PR118/PR122分支引用，不启动对方工作区writer。旧模块保留准确原始字节，新接线仅新增独立路径。governance/features.json只追加既有SAAS_AI_PRICING登记。

## 初始批次实际代码（历史记录）

- community_stage_runtime.py：原Phase1 DemoService和Phase2 OfflineSaas统一dispatch；Principal及门店绑定从服务端配置取得，客户端不能指定租户/角色/支付成功；所有广告及报价时间使用服务端时钟。
- community_stage_local.py：复用原orders/merchant/ad/refund/module/SaaS-order数据库格式，持久打开并验证；原组件的独立文件仍保留，不虚称跨库原子事务。私有目录、数据库符号链接拒绝、排他进程锁、失败释放句柄；不自动seed、不迁移生产数据。
- /offline/community-stage：商家展示、小程序流程、H5流程、商家与平台读视图、SaaS目录/订单/恢复共用同一HTTP服务。旧SaaS编辑、审核页面仍在/offline/saas-panel。
- clients/community-mini：真实微信开发者工具项目结构，既有AppID；wx.request对接同一服务的模拟订单与两个广告位。令牌仅内存，不保存密钥，不调用requestPayment。开发配置仅本机HTTP，不是微信发布工程验收。
- 原订单SUCCESS只生成MOCK_PAID_SIMULATED结果；成功广告必须读取原订单持久状态且经过原广告审批/有效期筛选。模拟结算操作仅Python测试操作员hook，禁止HTTP调用。没有真钱效果或Finance入账。

## 当前证据口径（2026-10-18）

已核验基线为 `d9dda1bf`（短SHA）、Hosted Run `39058998739` / Job `117472902513` SUCCESS：565项community、342项Stage5、258项Node测试。该回执只覆盖该基线；后续源码必须绑定新的确切CI，不得沿用基线PASS。`mini-python-runtime`、`mini-runtime`、`mini-sdk`、`mini-preview`均SKIPPED，不是官方编译、真机、生产接线或独立审核PASS。

本文件按时间保留研发历史。历史段落中的“尚无消费端”“未接线”“不调用requestPayment”等只描述当时状态，不覆盖下列当前源码索引；旧预览回执也不覆盖已修改的小程序源文件。缺少当前现场回执不等于账号、商户或凭据不存在。第一、二阶段仍PARTIAL，P1-05仍OWNER_DEFERRED，不作为本轮完成条件。

当前已有 `community_mini_application.py` 的原Center组合与受保护配置入口；`community_mini_center_identity.py`、`community_center_operations.py`、`community_merchant_opening.py`复用既有身份/项目/开通记录。`community_saas_finance_authority.py`提供权威公钥配置下的确认/冲正验签，`community_saas_fulfillment.py`提供原库兑现/恢复接线；`tests/test_community_saas_finance_integration.py`是合成签名与原SQLite组合证据，不是真实Finance签发或权益验收。支付、退款、分账适配源码已存在，未授权的现场资金调用仍HOLD。

## 40节点追踪

2026-10-17续接：community_saas_reconciliation.reconcile将既有通知RSA/AES验证与PartnerOrderReader单次签名GET查单交叉核对，要求同商户、服务端冻结订单/金额/币种及同SUCCESS交易号。网络前后复核绑定，网络期间不占写锁；查单后重新检查通知时效。原通知事件碰撞检查继续复用；通知候选与查单匹配证据分别保存为原saas_review_tasks中的FINANCE_EVIDENCE，独立确定ID与原created_at/已终结状态保留。第二次提交失败只保留候选，明确再次调用可完成，不自动重试。11项本地真实RSA/AES/SQLite测试含并发新连接、重开和中断恢复；网络报文为合成fixture。新增测试纳入Hosted与国内隔离回归，准确新CI终态另记。该接线仅补齐P2-11至13的核对证据，不是权威Finance确认、真实结算或生产验收，未开放HTTP或资金操作。

责任：ChatGPT负责本批独立接线；既有模块归属及独审结果不变。以下是源码证据状态，不是审核PASS。

| 节点 | 源码/集成现状 | 测试证据或下一依赖 |
|---|---|---|
|P1-01|服务端Principal绑定既有Tenant/Merchant/Store；补齐商家入驻入口、资料与独立审核链|入驻流程拆为下列子项；现场CRM开通绑定待验|
|P1-02|既有商家目录统一HTTP|新增真实Chromium商家读取|
|P1-03|原签名场景与金额校验复用|二维码签名→原订单；实体微信扫码预览待验|
|P1-04|原生小程序工程及请求客户端；历史开发预览上传成功|旧Run39006945633不覆盖当前源码；本候选官方编译/预览及真机待验|
|P1-05|OWNER_DEFERRED：公众号暂缓|2026-10-17 Owner明确不作为本轮完成条件|
|P1-06|原持久订单状态机复用|重新打开后原订单/事件保留|
|P1-07|统一loopback HTTP及受保护Unix代理候选|HTTP/Chromium源码测试；实际HTTPS宿主接线待验|
|P1-08|原生小程序客户端及H5客户端|金额/旧响应/伪成功拒绝|
|P1-09|原商家编辑/订单/广告复用|服务端角色和门店绑定|
|P1-10|原平台审核/审计复用|商家不可调用平台审核|
|P1-11|前后广告按原订单状态读取|成功/等待/过期/故障降级|
|P1-12|原退款/分账/对账预览复用|101=退款11+分配90；实际结算UNKNOWN|
|P1-13|五视图共用同一订单端到端|新增Chromium测试；非微信设备E2E|
|P1-14|进程锁、重开、权限异常|新持久host与既有恢复回归|
|P1-15|原专用CI执行整阶段源码回归|当前已核验基线见上；后续提交另核CI，不送断点审|
|P2-01|原报价API接入统一HTTP|既有Phase2全量回归|
|P2-02|原SaaS订单API接入统一HTTP|不替代消费者收款订单|
|P2-03|原权益读取及受保护兑现接口复用|合成Finance签名测试；未验收真实正式权益发放|
|P2-04|原后台审核API复用|权限/任务状态回归|
|P2-05|既有Center账号、会话、项目权限；新增受保护微信code绑定HTTP|原Center实例组合测试；现场账号/KMS/HTTPS接入待验|
|P2-06|原SaaS市场页面保留|原Chromium市场测试|
|P2-07|原CNY/USD多方案报价复用|既有价格及脱敏回归|
|P2-08|原客户订单中心复用|原浏览器报价→订单测试|
|P2-09|原续费计划及页面复用|真实确认Finance外部依赖|
|P2-10|原Owner定价编辑审批复用|真实Owner认证未验|
|P2-11|原证据接口及SignedFinanceAuthority确认/冲正验签源码|原财务权威签发方、信任公钥与tenant范围的现场接线待验|
|P2-12|支付凭证真实验签|新增原始报文RSA验签与AES-GCM解密源码；真实公钥/公钥ID与绑定待核|
|P2-13|原订单事件/Quote哈希关联复用|真实结算事件外部依赖|
|P2-14|原权益intent及SaasFulfillment原库兑现/恢复接线|合成签名、持久预留与重开测试；真实财务确认及grant权限待验|
|P2-15|原退款预审、提供商操作与独立Finance冲正验签接线|原库恢复测试；真实退款/冲正保持HOLD|
|P2-16|原精确schema验证复用|旧生产DB迁移源与授权待提供|
|P2-17|原跨库审计复用|没有跨文件原子提交声明|
|P2-18|原WAL/中断恢复+新运行时重开|真实主机故障注入未验|
|P2-19|原并发幂等+本批单进程锁|并发、重复退款与重复事件回归|
|P2-20|原备份复用；六业务库维护态快照和新目录恢复|SQLite源码回归不等于主机灾备验收；Center及原密钥恢复由既有宿主负责|
|P2-21|原package保留；新增确定性源码ZIP含运行时/页面/小程序/测试和逐文件Manifest|源码包逐字节校验；不构成生产安装包|
|P2-22|原服务端受保护配置与内存令牌复用|当前候选宿主注入与密钥恢复证据待验；不推断已有Secrets不存在|
|P2-23|原health/rollback_preview复用|真实安装/回滚HOLD|
|P2-24|小程序工程与历史开发预览回执保留|本候选编译/扫码/现场登录待验；公众号OAuth按Owner暂缓|
|P2-25|已有显式启用的提供商支付/退款/分账适配源码|当前候选商户绑定/产品权限/授权真实交易验收待核；本次不调用资金API|

## 12组与40叶交叉索引

此表沿用 `community-progress/scope.json` 的原12组及上表原40叶，是按描述和共同代码/验收依赖建立的多对多导航，不是新的权威需求树，也不是一一对应或完成证明。P1/P2前缀分别保留各原清单的编号语境，跨阶段关联不改原分组。原12组中的社区生命周期、员工细粒度权限及通知等细目没有单独的40叶编号；下列近似关联不能替代这些原组的独立验收。共享工程门禁聚合在P2-G，并同样约束其他组；不能据此重复计算完成率。

| 原组 | 关联原叶（多对多） | 阶段验收状态 |
|---|---|---|
|P1-A 原身份体系及用户资料关联|P1-01、P2-05、P2-22|PARTIAL|
|P1-B 商家入驻及微信进件资料|P1-01、P1-09、P2-05、P2-25|PARTIAL|
|P1-C 平台审核及特约商户状态同步|P1-01、P1-10、P2-04、P2-25|PARTIAL|
|P1-D 商家工作台门店员工商品|P1-02、P1-09|PARTIAL|
|P1-E 平台基础管理通知隔离|P1-10、P1-14、P2-04、P2-05|PARTIAL|
|P2-A 消费者交易及归属|P1-03、P1-04、P1-06、P1-08、P1-11、P2-05、P2-12、P2-24|PARTIAL|
|P2-B 定价订单及账务查询|P2-01、P2-02、P2-03、P2-06、P2-07、P2-08、P2-09、P2-10、P2-11、P2-13、P2-14|PARTIAL|
|P2-C 真实微信支付退款与对账|P1-12、P2-11、P2-12、P2-13、P2-15、P2-25|PARTIAL|
|P2-D 社区管理|P1-02、P1-09、P1-10、P2-05|PARTIAL|
|P2-E 版本化分账规则执行恢复|P1-12、P2-13、P2-15、P2-17、P2-18、P2-19、P2-25|PARTIAL|
|P2-F 运营财务后台|P1-10、P1-12、P2-04、P2-10、P2-11、P2-13、P2-15、P2-17|PARTIAL|
|P2-G 完整业务链集成|P1-05、P1-07、P1-13、P1-14、P1-15、P2-16、P2-17、P2-18、P2-19、P2-20、P2-21、P2-22、P2-23、P2-24|PARTIAL|

P1-05只作为历史范围索引，状态为OWNER_DEFERRED，不是本轮阻塞。所有40叶均有导航关联，但“被索引”不代表源码/现场/审核均完成；原组仍全部PARTIAL。

## 当前候选的一次性外部接线验收材料

只需要既有责任方提供脱敏配置引用和同版本验收结果，不要求复制秘密、新建账号/账本或推断既有配置缺失：

- 小程序发布/运维负责人：官方编译/开发预览 `receipt.json`、相同客户端source_hashes与真机扫码/登录/查询恢复结果。既有工作流的 `[mini-preview]` 会触发国内self-hosted预览并使用原Secrets；本次未触发，历史回执不能代替当前验收。
- 原Center/CRM负责人：与 `COMMUNITY_PINNED_DEPENDENCIES_20261017.json` 相容的宿主版本，现有verified账号/项目/租户/客户/合同订单引用及实时角色；scene与Principal、门店、onboarding_required映射。原 `Center.import_authority` 签名快照接线与撤权应在目标宿主验证，不新建第二IAM/CRM。
- 原安全/客户中心运维：现有active_key与历史index_key可用、恢复结果；原scanner对合规材料明确返回True、未知/失败拒绝的回执。接口见 `pr122_customer_core.py` 与 `community_project_materials.py`；只交key ID/状态，不交密钥或真实私有资料。
- 部署负责人：`MiniApplication.listen_proxy` 对应的固定HTTPS origin、TLS路由、非root运行、Unix socket与Nginx UID/GID/可信peer边界回执，以及微信请求域名与回调可达性。loopback测试不构成生产部署。
- 微信服务商负责人：现有sp_mchid/sp_appid/sub_mchid可信绑定、产品权限、公钥ID/可信来源与商户证书配对状态；固定回调、分账接收方/比例限额/enabled_operations政策。契约见 `community_wechat_sp_readonly.py`、`community_mini_payments.py`、`community_wechat_sp_actions.py`；秘密继续由原受保护宿主注入，真实资金执行另需许可。
- 原Finance负责人：authority_id、签名key_id/公钥与tenant范围、原系统签发的确认/冲正契约及旧价版本/perpetual映射。契约见 `community_saas_finance_authority.py` 与 `community_saas_fulfillment.py`；合成签名测试不代替真实权威签发，微信验签不代替Finance核销。

验收顺序：冻结最终源码与依赖→对应SHA完整Hosted与源码包核验→上述无资金接线/撤权/资料/恢复验收→同客户端hash官方编译和真机→最终候选集中独立审核。真实发布及小额支付/退款/分账只在另有明确执行许可和权威Finance核对条件后进行。本材料不授予发布、资金或持久权限扩展许可。

## 可复现验证

### P1-01商家入驻补齐（2026-10-17 Owner指出遗漏）

原有community_onboarding_offline只有离线状态函数，不能视为商家入口/资料上传/后台审核已经接通。本轮沿用该原状态机和onboarding/onboarding_events两张业务表，纳入既有Center数据库的备份域；原accounts/sessions/projects/objects/versions/links/audit、加密密钥与扫描器复用，core源码固定字节不改，不新建账号库、材料目录或审核队列。不把申请人伪装成已有签约项目：已经验证的原账号即能申请，正式项目与门店权限仍由原CRM权威绑定。

|子项|实现及边界|
|---|---|
|入驻入口|MiniApplication配置onboarding后提供/merchant/join；/merchant/review为审核页，数据另作会话/权限检查。默认不配置则路由关闭。仅候选源码，不代表已发布到官网。|
|主体与资料|企业/个体工商户；主体名称、门店名称、经营地址、联系信息；执照、经营者/法人证件正反面、门头、经营场所、结算账户证明。委托办理追加授权书及经办人证明；餐饮食品追加行业许可。此为本平台业务清单，不冒充微信官方进件规则。|
|私有上传|PDF/PNG/JPEG每份≤5MB，原扫描器必须明确CLEAN；复用原加密对象与版本记录，客户端不能指定磁盘路径、对象ID、扫描结果或审核主体。资料及申请内容/审核意见加密，列表不返回对象ID。|
|申请与补件|草稿、提交、审核中、要求补件、修改重提、驳回、通过；CAS版本检查、补件原因、资料过期拒绝提交/通过、保留旧材料版本。|
|后台审核|保护配置指向原已验证账号与REVIEWER项目角色，每次原会话/CSRF及项目撤权检查；申请人不能自审。每份资料独立通过/补件，整单通过必须每个当前必交材料均已独立核验；更换资料清除旧审核结果。|
|开通边界|APPROVED为业务入驻通过；没有原CRM映射时显示AWAITING_CRM_BINDING。受保护映射齐全且唯一时自动开通工作台；多个既有映射由审核员选择，不接收客户端自报租户/角色/门店。微信仍为NOT_VERIFIED，不创建sub_mchid或开放收款。|
|真实接线与回归|同源POST/merchant/onboarding复用原__Host-xj_customer与X-CSRF-Token，亦接受受保护X-Center-*后端接线；先认证大文件请求再读体。原客户中心host将当前CSRF注入configureCommunityOnboarding，无新登录表单或令牌存储。真实Chromium→HTTP→原加密SQLite测试覆盖申请、6资料上传、逐份审核、补件重提、通过及360/768/1440宽度。扫描器/账号/文件为合成fixture，非生产资料验收。|

另补CenterOperations：商家、店员、平台审核与财务只读使用原会话/CSRF及逐次项目权限；保护配置精确绑定原user_id、项目允许角色与已注册Principal/门店。项目成员不自动继承商家或平台角色，撤权、epoch失效及作用域变更拒绝；原限流和审计复用。/community/operations默认关闭，只开放原community.*工作台操作，不接管SaaS/Finance管理。业务库执行与Center审计不声明跨库原子性，未知不自动重试。完整CI及国内回归绑定准确提交后另记录。

### 入驻通过后的工作台开通接线

MiniApplication先configure_onboarding，再configure_operations；新商家原CRM授予的精确账号/项目/已注册Principal映射须带onboarding_required=true。CenterOperations每次使用新商家权限前验证原入驻APPROVED版本、所有当前必交材料的审核与有效期、原项目实时权限及已完成开通记录；申请字段不能授予角色。原已准入商家可保留原受保护映射，不反向认领历史门店。

community_merchant_opening复用原Center.links/audit及原merchant_profiles，不增加第二权限库或任务队列。先独占持久RESERVED记录绑定application/原账号/project/tenant-merchant-store/版本/workspace，再写原商家档案，最后记录OPENED；档案初始PAUSED，微信收款仍关闭。既有无本申请保留记录的商家档案拒绝认领。开通中断/结果未知保持OPENING_PENDING且权限拒绝；审核员显式open_workbench恢复同一记录，不能换申请/作用域、覆盖其他商家或使停用记录复活。已完成重放不覆盖商家之后的编辑。

审核员可要求已通过申请重新核验；此时原版本立即失去工作台访问。补件与独立审核完成后，必须有同一申请原CORRECTION事件、递增的新批准版本及同一CRM映射，才更新原开通记录并恢复，保留商家已编辑档案；缺失旧档案或绑定变化拒绝。没有跨数据库原子提交声明，保留状态和显式恢复为实际语义。14项原SQLite测试覆盖前后提交中断、新连接恢复、同店重复申请、历史档案抢占、撤权、资料过期、重新核验和恢复；两条真实Chromium/HTTP流程分别验证无CRM映射与已绑定自动开通，并实际调用新商家工作台订单接口。均为合成身份、资料和映射，实际部署/真实CRM交付仍未验收。

### 入驻列表与身份切换补齐

原100条上限报错改为50条/页、服务端固定参数游标、可选状态筛选；申请人列表始终按当前原Center账号约束，审核列表每页重新检查原REVIEWER项目权限。游标只接受已生成申请ID格式，状态固定枚举，拒绝客户端自报owner/任意SQL片段。返回next_cursor供页面“加载更多”使用；列表不是不可变快照，刷新后按最新记录重新读取。3项原数据库测试用61条合成记录覆盖两页、去重、状态筛选、账号隔离和无效输入。

原客户中心宿主须在登录、退出、切换账号时调用configureCommunityOnboarding传递当前CSRF或空值。页面递增会话代次，立即清除私有列表、申请详情、材料、表单及工作台选项；旧请求的响应和错误不能改写新账号视图。上传在读取文件前固定申请/版本/会话代次，读取后再检查；身份变化时不得把旧文件携带新账号凭据上传。2项Chromium客户端测试使用明确的延迟合成transport分别覆盖旧资料响应迟到和文件读取中换号；与原2项真实HTTP/SQLite流程分开记录，不冒充真实跨账号生产验证。新测试纳入原完整CI；分页测试亦纳入国内非root回归，不另开审核。

python -B -m unittest discover -s tests -p 'test_community_*.py'
python -B -m unittest discover -s tests -p 'test_stage5_*.py'
node --test clients/community-mini/client.test.cjs demos/community-local-e2e/*.test.mjs demos/community-payment/demo.test.mjs demos/community-admin/admin.test.mjs

Playwright固定1.55.0并安装Chromium；缺少浏览器不允许标完整PASS。精确版本与GitHub实际CI回执在Issue76记录。

## 尚不能关闭的阶段门禁

PHASE1_FULL_ACCEPTANCE=NO；PHASE2_FULL_ACCEPTANCE=NO。小程序开发预览已上传成功；原Center Identity源码组合已实现，现场实例与微信真机登录仍未验收。权威Finance消费端及原库兑现源码已存在；真实Finance签发方/信任配置与兑现现场验收、旧生产DB迁移契约及目标宿主安装/回滚制品仍缺。独立审核只在完整阶段候选和全部证据齐备后集中提出。本批不是完整阶段交付，也不是新的审核申请。

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

旧国内Job117327880511现已FAILED，停止于checkout，应用测试未运行；新任务可在其退出后启动。补齐Unix宿主实际权限约束：必须非root应用用户，socket父目录group必须为配置的Nginx group，跨UID代理时须具备组遍历/读取权限，拒绝0700目录造成假就绪。新增拒绝缺少代理组遍历权限检查；CI与国内均使用非root身份实测。


### 商家工作台功能开发（2026-10-17 15:40后）

新增/merchant/workbench及独立workbench.html/css/js，使用原客户中心会话Cookie和X-CSRF-Token，宿主调用configureCommunityWorkbench({csrf,workspace})注入已授权工作台名称。没有角色选择器、演示业务数据或第二登录系统。默认不配置CenterOperations则路由关闭；登录/退出/切换账号须由宿主重新配置，立即清除资料和旧响应。页面复用原CenterOperations的逐次项目权限、入驻准入、限流和审计。

已新增订单分页及状态筛选、当前筛选页CSV导出（整数分、模拟状态与未验结算标志、表格公式转义），员工可查订单但不能导出。门店设置读模型允许已开通的PAUSED门店读取并以原version保存资料，不再依赖仅供公开展示的ACTIVE接口。商品编辑与上下架复用原catalog_items；广告草稿创建、版本化状态变更、平台独立审核、有效时间与事件报表接原广告库；商家不可用页面按钮越过服务端平台权限。报表按门店、半开时间区间及游标分页，只统计原已记录事件，零展示点击率返回null，不代表独立访客或收入。对账仅原模拟预览，不发起资金操作。页面无生产权限授予，现场客户中心host接入与真实商户验收仍待交付。


### 未完成功能继续编码（2026-10-17 15:54后）

新增order_detail原库读模型与工作台订单详情入口，显示原状态事件、原退款预审记录、剩余可预审金额及截断标志。商家页面可提交原refund_record并读取持久结果，重复请求编号仍由原日志幂等处理；结果未知不能换编号盲目再提交。分账表单接原split_preview，20个以内接收方编号/基点，原服务端校验总比例与余数分配，按原订单扣除退款预审计算。仅预审与方案计算，不称实际退款/实际分账。新增真实HTTP/Chromium流程操作退款250/1250后，分配余款1000为900/100；合成付款事件，非真实资金。

新增community_wechat_sp_prepay.PartnerPrepay：实现普通服务商JSAPI小程序预支付POST、请求RSA签名、微信响应原始字节验签、prepay_id校验与小程序调起支付RSA参数签名。协议来源https://pay.wechatpay.cn/doc/v3/partner/4012759974。保护配置冻结原账号/项目、服务商小程序、特约商户、订单号、CNY整数分、用户sp_openid、HTTPS通知地址与分账标识；公开请求不能自报这些字段。复用原PartnerOrderReader密钥加载及固定HTTPS/禁代理/禁重定向/超时传输。复用原Center会话/CSRF和项目实时权限；网络前原events持久消费服务商订单号，网络后再次检查账号/项目/冻结绑定；结果加密保存在原links，不建第二订单或Finance账本。未知不重发；existing只读取已验签持久结果并重签客户端参数，不调用网络。已消费但无持久成功结果返回UNKNOWN，需要原查单与后续人工/权威协调，不自动重下单。客户端参数只表示等待用户确认，不能当作已支付或发放权益。6项新增真实RSA/SQLite测试使用合成提供商报文，不读取现场Secrets；源码接线未注册HTTP、未在生产启用、未向微信实际下单。消费者原订单权威映射、原生按钮接线与Finance确认仍需完成后才能关闭真实支付门禁。


### 消费者付款按钮及动态原订单接线（2026-10-17 16:04后）

新增community_mini_payments.MiniPayments，MiniApplication.configure_payments为受保护宿主显式配置入口。/mini/payment默认404；启用后仅接受原小程序Bearer会话，拒绝Cookie/Center凭据混用及客户端商户/金额字段；prepare、recover、query每次复核原客户订单归属、PENDING状态、整数分、当前原Center项目权限及实际微信付款身份。原session加密metadata保存可信换码得到的openid，客户端不返回openid/session_key；原有旧会话仍能访问原只读接口，但动态支付须重新可信登录取得加密付款身份。

支持既有冻结订单配置及动态门店配置二选一；merchants按原scene保护配置sp_appid/sub_mchid/description/notify_url/profit_sharing，并固定原project和原tenant/merchant/store。动态订单号由服务商、原门店作用域和原reference确定生成32字符，不接受客户端自报支付单号；金额来自原orders、付款人来自原加密Mini会话，不需逐笔人工配置。网络前后绑定复核；原Center持久attempt防止重发，原links加密结果支持实际数据库重开后恢复。query复用原PartnerOrderReader真实GET签名和响应验签，SUCCESS仅显示微信已支付观察，原模拟订单不会被伪改SUCCESS，Finance未核销、不生成财务凭证、不发放权益。

原生payment.js与checkout页面新增显式“微信支付/恢复原支付单/查询微信结果”。session.payment使用独立/mini/payment及显式enabled响应；UI配置configureService(url,true)仅显示入口，服务端原身份与绑定准入仍不可绕过。默认payments=false保留原开发模式。准备结果迟到/身份或订单变更不调用requestPayment；并发点击拒绝；取消/SDK成功均只查询原订单，不自行认定支付成功；未知不重试prepare。7项新增Node支付流程测试、2项session支付运输检查、6项原Center/SQLite/HTTP集成测试（含动态绑定与实际重开）验证这些新增代码；网络、账号及商户为明确合成fixture，不是现场交易验收。原生源文件已变更，旧预览回执不再当作本版编译证据；新编译/预览终态按准确CI另记。


### 第二阶段原客户中心SaaS业务接线（2026-10-17 16:29后）

新增community_center_saas.CenterSaas与/customer/saas页面、/customer/saas-api，MiniApplication.configure_saas显式装配。默认不配置则页面/API关闭。复用原Center账户/会话/CSRF/项目成员与原StageRuntime/OfflineSaas/报价和订单库，不新建IAM、订单或财务库。客户工作台保护映射精确绑定原user_id/project/已注册CUSTOMER Principal，逐次核对原项目OWNER/EDITOR与租户，拒绝权限、Principal或作用域变化；原限流和审计复用。

报价编号服务端生成，固定30分钟报价期限；在原Center.links加密保留报价归属，再调用原报价函数。订单号由原报价/币种/租户确定，先保存原Center归属再调用原订单准备，重复准备只读取同一原订单，部分结果未知不盲目重新创建。客户不能自报租户、用户、quote_id/order_id创建或财务证明，不能读取或认领历史未关联记录。同租户同项目的第二客户也不能读别人的报价、订单、状态和续费计划。本人报价/订单记录50条游标分页，原数据库重开后可恢复。Center元数据和原报价/订单SQLite不是跨库ACID，保留未完成归属记录，不伪造业务成功。

客户页面支持模块目录、方案费用明细、人民币/美元价格、报价、币种选择、订单准备、本人记录和续费查询。未获得原CONFIRMED_EXTERNAL的订单明确显示AWAITING_FINANCE_CONFIRMATION，不生成续费权益。宿主登录/退出/账号切换调用configureCommunitySaas({csrf,workspace})，清空报价、订单、表单、成本字段和旧响应。页面不存令牌、不另建登录。

平台Owner定价同样接原客户中心会话：受保护PLATFORM_OWNER映射还须有原项目OWNER角色，普通客户及仅EDITOR无权创建/批准方案。页面支持多费用组成、CNY/USD售价与成本、一次/月/年/用量周期、月付/年付/买断/免费/优惠/计量/定制及第三方费用支付方；买断/免费不传周期天数。审批与成本凭据继续交原offer审批函数，不伪造生产发布许可。新增6项原Center/SQLite业务测试与1条真实HTTP/Chromium客户+Owner流程验证这些新代码（身份/价格均合成），含同租户第二客户拒绝、重开、过期、原Owner权限、报价→订单→恢复、费用编辑与批准及三尺寸布局。Finance权威消费端仍未在检索的现有源码中找到，不能用测试HMAC或Owner按钮代替实际财务确认。

续费提案只读取原module_entitlements的实际valid_until，不接受客户端自报原到期时间；仍须原CONFIRMED_EXTERNAL才生成提案，不执行自动续费。Owner可读取含成本的原方案并复制到新版本草稿，普通客户仍被拒绝，原版本不可覆盖、原批准不继承。原方案中按租户限制的tenant_scope也需保持，不能复制时扩大可见范围。

### 分账账单剩余契约与证据边界（2026-10-18）

普通服务商申请分账账单接口（https://pay.wechatpay.cn/doc/v3/partner/4012761140）返回按日整文件下载地址及摘要，不提供分页游标。完整下载字节通过已验签ticket的SHA1核验，加上明细行数与汇总总条数一致，只证明取得该文件及其结构完整；工作台50行展示分页不是提供商全集证明。新记录将已校验的5列汇总原值保留在原加密账单payload中，公开回执仅给留存状态；旧记录缺少原值时明确标记，不反推生成。汇总金额仍为NOT_RECONCILED，Finance仍UNCONFIRMED。

尚需以下最小权威契约/证据，未取得前不推断业务规则：

1. 汇总分类公式：分账成功出资金、失败已转回、解冻及回退各列的明细类别、状态、符号与跨日归属，尤其失败转回的入账规则。官方样本（https://pay.wechatpay.cn/doc/v3/partner/4012075366）只能验证该样本算术，不能覆盖未展示的失败情形。
2. 时间与账单日：CSV“分账时间”对应创建/完成/入账中的哪个事件、时区及日边界。通用参数规则（https://pay.wechatpay.cn/doc/v3/partner/4012081935）提到北京时间，但没有直接定义该CSV列与RFC3339 finish_time的关系。
3. 回退明细映射：CSV中回退行的参与方方向、微信分账/回退单号和分账明细单号各自对应哪个API字段。回退查询（https://pay.wechatpay.cn/doc/v3/partner/4012466858）明确return_id、out_return_no和return_mchid，但未给出CSV detail_id关联。解冻同样缺少对应明细契约。
4. 反向全集证据：准确商户/作用域/账单日的本地成功明细全集、截止点及完整性证明；仅扫描当前active加密记录无法证明历史无遗漏或无外部渠道交易。需先确定第2项的日期归属才能判定“本地应有但账单缺失”。

以上缺项不会由样本金额相加、接收方账号外形、假定北京时间或工作台翻页完成来替代；已证明的分出逐接收方身份/金额核对仍可运行，但不能据此给出整日全量对账成功或正式财务验收。

## 2026-10-19 Owner接续：原阶段功能闭合与证据边界

沿用原Issue76、原开发分支和上文12组/40叶索引。源码接续依据为原
DEVELOPMENT_CHECKPOINT中的前任Writer交接及Owner本轮明确开发指令；
不改官网/P2分支，不运行生产或真实资金，不停止独立监督的README/status更新。
提交使用最新原分支HEAD的非强制CAS，保留监督并发提交。以下为本次代码候选，
不是独立审核、安装或整阶段验收结论；最终准确源码、CI及测试结果须另行绑定。

- P1-D/P2-A：原商品目录首屏接口兼容，增加消费端100项、工作台200项的
  keyset分页与加载更多；稀疏未定价页仍前移游标，重读时保留原账号/项目/门店权限。
  小程序会话切换与页面卸载必须丢弃旧目录响应，不能把前一身份的商品加入新页面。
- P1-D/P1-E：落实已有Staff.READ_OPERATIONS的门店资料只读委派；
  仅原持久且当前有效的明确委派可读取，不借用商家角色，不开放编辑或其他操作。
  未委派静态员工继续拒绝；原商家Principal/门店绑定、OWNER角色和员工权限撤销实时生效。
- P2-D/P2-F：社区订单报表复用原财务退款历史校验，不再另写宽松累计；
  非整数、布尔、非正退款、不可读历史及超过原付款总额均拒绝，仍不产生Finance确认。

### 账单原始定义复核（本轮不扩大已通过范围）

重新核对微信普通服务商官方申请/下载账单、分账查询、回退查询、解冻及通用参数页面。
官方样例XLSX的SHA256仍为
`4091e88e5c39a30b781b76f6c733e4fa495c61f7ec4e397c6117cbc4a7de89ff`。
`sample_arithmetic`仅诊断该样例展示的三个成功分类算术：分出、解冻加逾期解冻、回退。
它只返回分类差异标签，不公开账单金额原值或接收方资料；非零失败转回保持语义未定义。
`establishes_reconciliation=false`、`summary_amounts=NOT_RECONCILED`、
`finance_status=UNCONFIRMED`及禁止资金自动重试不变。样例一致不能变成全账对账PASS。
旧记录未留存汇总时明确UNAVAILABLE_LEGACY_SUMMARY，不反算补写旧数据。

下列缺项仍必须由准确官方字段合同/既有责任方证据解决，不能靠重复跑源码测试解决：
1. CSV分账时间对应创建、完成或入账事件及bill_date跨日归属。通用参数规定UTC+08，
   但没有直接建立CSV列到finish_time的映射。
2. 非零失败已转回的汇总分类、符号及跨日规则；官方样例仅为零值。
3. 回退/解冻CSV的参与方方向和分账明细单号映射。回退API有return_id但没有detail_id；
   不能假定CSV该列等于return_id或原split detail_id。主动解冻证据不覆盖自动逾期解冻。
4. 上述日期合同下的本地完整成功明细全集及截止点。当前active记录扫描不证明历史全集。

来源（2026-10-19北京时间复核）：
- https://pay.wechatpay.cn/doc/v3/partner/4012761140
- https://pay.wechatpay.cn/doc/v3/partner/4012075366
- https://pay.wechatpay.cn/doc/v3/partner/4012081935
- https://pay.wechatpay.cn/doc/v3/partner/4012466850
- https://pay.wechatpay.cn/doc/v3/partner/4012466858
- https://pay.wechatpay.cn/doc/v3/partner/4012466860
- https://pay.wechatpay.cn/doc/v3/partner/4014547107

以上沿用原外部缺项清单，不新建审批流程，不重审未变已通过范围，也不把待定字段改为PASS。

### 同批原流程恢复与完整性修复

- P2-A/P2-C：原商品购买在Center库存预留后订单库写入中断，使用原reference和冻结明细
  显式恢复，不重复扣库存，不重读现价生成第二笔订单；小程序提供原单恢复入口。
  已由可信微信状态投影CLOSED的订单按原购物篮所有者释放库存，重放/重启不重复释放。
  取消尚UNKNOWN时不得再次签发付款参数；查单和原取消恢复路径继续保留。
- P2-B：原SaaS报价/订单跨库预留中断使用原ID恢复，严格匹配原拥有者、报价、
  价格来源指纹及有效期，不把未知或过期价格补写成有效新报价。
- P2-D/P2-F：收益读视图校验原分账请求、冻结规则分配、预算和每一回退的完整绑定；
  非整数、负值、重复回退、错项目/订单/接收方以及超额累计均拒绝。
  仍只显示提供商观察，不签发Finance确认。
- P2-C：账单下载网络返回后再次核对原授权身份和作用域，防止同政策下切换授权
  仍写入旧商户账单；来源校验与现有只读资金边界保留。
- P1-B/P1-C：可信当前微信查询确认为APPLYMENT_STATE_REJECTED后打开补正，
  保留原business_code和拒绝回执，再经原内部审核才允许同申请覆盖重提。
  未知提交不开放编辑/重复提交；每次被审核修订都有独立的一次性提交意图，
  查询期间资料版本变化则拒绝迟到结果。原平台审核和资料有效性继续实时核对。
  官方合同：https://pay.wechatpay.cn/doc/v3/partner/4012697168
  及 https://pay.wechatpay.cn/doc/v3/partner/4012062379 。

所有新增网络边界测试使用合成返回或合成签名；没有真实资金、进件、部署或客户验收。

### 原叶仍缺的交付契约

P2-16现有精确DDL守卫并非旧生产库迁移器。需要原旧库版本、脱敏结构与字段/数据映射，
才能实现并验证迁移；不能对未知生产库猜测DROP/ALTER。
P2-21/P2-23当前制品明确为OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE；
原rollback_preview和新目录恢复不含目标宿主安装、在线版本切换及原地回滚。
这些实现须绑定既有目标运行时、目录、服务、备份职责契约，不能以源码ZIP通过代替。
上述两类既有原叶保持未完成，不另建任务树；P1-05仍OWNER_DEFERRED。

- P1-D/P1-E/P2-F追加撤权恢复：门店编辑逐一复核目标workspace原角色权限，
  不能借入口EDITOR权限操作仅OWNER目标。平台客户/审计不因无关商家撤权全页失败；
  商家及订单汇总明确未覆盖映射和ACCESSIBLE_STORE_SUBTOTAL，拒绝伪称完整总额。
- 微信覆盖重提若结果UNKNOWN，后续旧REJECTED回包不再次开放补正；
  当前提供商状态非REJECTED时不得凭历史拒绝回执覆盖提交。

本批本地完整community回归第一遍698项中671项通过、27项环境错误，
与原基线相同的Unix socket权限及Chromium/Playwright运行环境问题，不能写成全量PASS；
Stage5本地316项中310项通过、6项浏览器环境错误。冻结后新增专项另行通过，
最终完整结论以本提交准确SHA Hosted CI为准。不会因本地环境错误删测或降级安全边界。

### 第一批准确 Hosted 回执与随后增量

第一批提交 `f1325961bb9945c375a723087077184971edcfbe`，tree
`4754e74af22a016f4cb295d8468a3fbbfbaa936b`；44个文件，远端逐blob回读一致。
Hosted Run https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39152437043
于2026-10-19 02:07北京时间完成SUCCESS：744项community、342项Stage5、238项Mini/Key、
40/8/7项其余Node，共1379项执行通过。包括本地受环境限制的Unix socket与Chromium测试。
确定性源码包SHA256为`8c3ea3874ec1b955fd8639f3901ebe5071531fce0da649ae87c47dc73972ccfd`，
与本地冻结包一致。六个原Center源码依赖仍逐字节符合原pin。
这份回执不覆盖后续修复，也不代表外部正式独审、真机、安装或Finance验收。

随后交叉复核正在补齐：旧合法跨秒报价兼容、财务查单后授权身份变化、
同business_code旧applyment_id拒绝回包、损坏/缺失分账快照不可静默计零，
以及原项目反馈第201条以后的授权分页。未把第一批CI通过当作这些新差异通过。

### 第二批增量候选

项目反馈沿用原Center消息库、authorized_records全链来源及隐私授权校验，
增加(created,id)键分页；201条反馈可全部读出，保留原10,000条安全上限。
小程序加载更多、会话切换清理和原证据未知拒读均覆盖，不改pinned core。

财务查单返回后冻结并复核原scope/project/user，变更时不投影订单、不释放库存。
旧无指纹报价仅允许原预留到原固定到期之间的合法创建时间；新指纹报价仍严格原时刻和摘要。
收益视图对损坏action、缺失/失效冻结快照及服务缺失明确拒绝，不能静默返回零；
Staff管理前复验原商家Principal/tenant/runtime binding。

进件查询绑定business_code及applyment_id，记录已验签时间/签名指纹和已消耗凭证。
提交ACK按官方仅applyment_id响应schema核验，查询或错误回包不能冒充成功ACK；
同秒合法响应及允许时钟偏差正常处理，不把本地墙钟当提供商业务代际。
未知覆盖提交出现可信新applyment_id时可以恢复；同ID旧拒绝或仅状态变化不足证明新代际，
保持UNKNOWN并禁止盲目再发，必须由权威提供商补足该次提交结果。
合同：https://pay.wechatpay.cn/doc/v3/partner/4012719997 。
此边界不影响正常已确认ACK后的再次审核拒绝/补正流程。

第二批冻结前本地Mini/Key275项通过；原进件共享传输回归794项中767项通过、
27项仍为已定位环境错误，最终两项重放专项加入后进件56项全部通过。
最终完整准确提交回执待对应Hosted CI核验，不继承第一批SHA为本批PASS。

### 第二批准确 Hosted 回执与最终交叉复核

第二批 `bd9a84ea5bea4189cfe6174daa333560af372159`，tree
`2efcbb31e1977dedf5adff551280daacdb36caf9`，21路径远端逐blob回读一致。
Run https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39153661204
于2026-10-19 02:24:52北京时间完成SUCCESS：798 community、342 Stage5、275 Mini/Key、
40/8/7其余Node，共1470项执行通过；源码ZIP SHA256
`3fbdc604d992304d50e3c5e8c853dd00b5b6c5c1fea40ee43952018cd4f4d4e2`与本地一致。
四项现场mini任务均SKIPPED。此回执不覆盖其后源码修复。

最终交叉复核另外发现跨申请进件ACK归属与健康检查依赖覆盖两处缺陷，继续修复，
不能因1470测试通过就关闭全部源码审核。`/community/health`是真实HTTP入口，
补齐原Center及已组合业务库连接检查；它只声明连接可用，不声明生产业务验收。

原交付缺项进一步限定：原Center已有证据表升级，P2-16缺的是社区六业务库旧版本
转换、校验和失败回退合同。完整远端树中的既有R4部署器固定Tokyo Portal单文件，
国内官网部署器仅内容指针/nginx/TLS，backend-migration仅OAuth库；它们不消费社区
MiniApplication/六库制品，不能作为P2-21/23已完成的证据。须复用既有发布体系并取得
社区宿主启动、服务切换、原Center及六库配套恢复契约后完成社区适配，不另造权限链。

第三批修复沿原Center同一写事务核对所有进件记录（包括inactive与历史ID/签名）归属。
首次提交冻结服务商域；已知ACK签名不能转用于其他申请，服务商域内applyment_id不能
跨application/business_code重复认领。旧缺域记录不当作其他服务商跳过；旧申请先由
可信同business_code查询补足域证据，不能仅凭当前本地配置重提。冲突保持UNKNOWN，
不自动补发。未曾观察过且POST ACK不回显business_code的响应，单靠签名时间不能
证明请求归属，仍需官方受保护请求/响应通道；没有宣称签名协议提供它未包含的字段。

### 第三批准确回执及最终责任核对补充

第三批 `9e92c6d090dab69b91324b348277f00bc1d5ae64`，tree
`68d660171b7b62b8e582552b2e9d19fd8d24cb25`；Run
https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39154788419
于2026-10-19 02:39:53北京时间完成SUCCESS：824 community、342 Stage5、275 Mini/Key、
40/8/7其余Node，共1496项执行通过。源码ZIP SHA256
`5b8bd154e5660cd62283aac53b25b2c6e8e28ec67c22250f6a6d5a23c1ff1ccf`与本地一致。
三批55个不同路径，现场mini四项SKIPPED。这不是全量代码或生产交付关闭。

责任核对纠正前文过宽的外部依赖描述：缺少实机不妨碍已知历史schema转换、账本候选
盘点及离线发布适配。原英国部署位置已有明确Owner决定，见
`plans/STAGE5_WECHAT_MERCHANT_STACK_REUSE_AND_SERVER_GATE_20261014.md`最终决定段；
国内3.11.6隔离验证不能改变该宿主约定。以下继续作为第四批增量实施，不继承第三批CI。

1. 账单：同一Center SQLite事务盘点原ACTION/RETURN（含inactive）、冻结加密清单及
   audit锚点；明确统计缺证、损坏绑定、非终态及成功候选。反向候选不能冒充该账单日
   缺行，完整SPLIT日请求仍明确拒绝。原store授权外或未知账单行仅返回安全常量，
   不泄露其他store交易号、订单、金额；读账单和写审计前后重验授权身份/解密权限。
2. 六库：`community_stage_migration.py`支持原Git历史精确DDL指纹，离线旧备份SHA及
   文件集验证、受限内存升级、原非空行/rowid/sequence逐类型守恒，合法旧冻结报价和
   历史审批继续继承。未知schema、缺失原治理/订单报价证据、bool/float金额类型混淆
   拒绝，不填猜测值。仅生成全新私有目标，源备份不写；故障/中断无完成标记。
   原Center备份恢复仍由原Center管理方负责，不另建IAM。
3. 发布：`community_release_candidate.py`复用原英国隔离容器与MiniApplication约定，
   校验确定性ZIP、六个Center pin及SBOM；离线真实写入source+六库generation，校验原
   Center配套备份，组合真实应用并检查HTTP维护态，再原子选择同一源码/数据代次。
   原代次配套回退、崩溃意图诊断和显式对账恢复有实际离线实现；持久化错误HOLD，
   不自动重放，不把恢复后的提交观察说成原调用收到成功回执。候选容器保持停止、
   network_mode:none，不构成生产启用脚本或已安装证明。

剩余最小合同与责任：
- 提供商CSV合同仍缺账单日归属/跨日终态、分账时间对应事件、summary各类计数/符号/
  金额公式、return/manual/expired-unfreeze列映射。官方样例及现有API未给出完整定义；
  由支付合同负责人取得提供商权威定义，不能以真实账单样本代替完整合同。
- 原账单是sub_mchid整商户范围，现Finance授权是store范围。整商户聚合的授权和覆盖
  范围须沿原权限设计明确；这是项目设计/授权范围问题，不是等待微信新增接口。
- 已识别Git历史六库不再笼统外阻。仅未知现场DDL或原历史缺失治理/报价证据需要对应
  现有系统负责人提供精确原记录，迁移不发明价目、审批或历史数据。
- 原Center必须可按现有构造同进程注入英国MiniApplication；若实际跨机，须原Center
  提供IdentityPort/服务鉴权合同，不能复制IAM或猜共享DB。image digest、运行身份、
  域名、资源配额及SecretRef是生产绑定值，不阻止本轮离线代码完成；现场切换、
  原Center恢复与真实业务验收仍未执行。

现有 `deploy/TASK_SUPERVISOR_RUNTIME.md`、`scripts/task_supervisor_runtime_entry.py`、
`canonical/PROJECT_STATE.md`的英国机械入口仅SCAN_COMPLETED_PROVIDER_NOT_ADMITTED，
不dispatch、不载入任意命令/插件；其release verifier固定task_supervisor三文件。
社区live激活仍须原controller提供社区release目标scope、lease/fence/epoch与ACK绑定
接口，才能复用原执行权，不得另起docker writer冒充既有通道。本轮离线发布不声称
已经补齐这个跨系统接口。

### 账单选择上下文补修（2026-10-19）

第四批后继续检查发现工作台日期/账单类型选择未隔离旧请求和分页。这是已有界面
行为缺陷，不依赖提供商账单语义合同。修复绑定选择代次与kind/bill_date，选择变化
清除两类分页及旧展示，迟到成功/失败不得污染当前选择；仅取消过期账单界面的
等待状态，旧请求收尾不得解锁新请求，改日期不得解锁未完成的资金操作。Node DOM回归覆盖读取、下载、核对、审计分页、
类型/日期切换、身份切换及错误恢复。准确提交Hosted终态另登记原Issue76；本段
不继承旧CI为本次PASS，不改变任何对账语义、权限或生产状态。

### 离线恢复持久化补修（2026-10-19）

继续核对既有发布/回滚适配发现，恢复六库通过普通文件写入后仅close，快照清单
亦仅close；最终同步目录不能替代文件数据同步。旧实现的定向故障注入中，恢复
路径即使所有Python fsync均抛错，仍返回restored=True，因为该路径没有调用fsync。
这不等于SQLite备份内部未同步，也不声称已复现真实断电数据丢失。

原snapshot/restore现分别同步其数据库和快照清单，再同步新目录及父目录；任何
屏障失败均不返回成功，仅清理本次新建目标，原源不写、既有目标不覆盖。restore
仍不复制snapshot.json到state，保留既有目录合同及非跨库原子声明。离线release
在原组合关闭后重新逐文件校验并同步完整generation，再保持原目录、元数据和
READY发布顺序；含组合生成的runtime.lock及可能更新的数据库，失败不返回成功。
安装开始即持久化INSTALLING失效标记，检查代次时遇此标记拒绝，待所有文件、
READY和目录同步成功才撤除；它不计入最终payload清单，不改变旧合法代次格式。
异常先尽力撤下READY，再尽力写HOLD，并始终保留原始错误；预置标记阻止READY
同步、清理和HOLD新建同时失败时被误认完成。若最后撤标记的目录同步及后续全部
修复写入都不可用，持久化状态仍UNKNOWN，不宣称绝对HOLD、持久删除或原调用成功。

新增定向测试覆盖数据文件/目录故障矩阵、源不变、全文件先于READY的顺序，以及
恢复失败早于HTTP探测、无READY/当前指针。测试中的合成健康返回仅验证持久化
失败及顺序，不冒充真实HTTP验收。原准确Hosted终态另登记Issue76；本补修不
提供live controller合同、不变更权限/账单语义、不声明生产安装或真实断电验收。

### 整商户财务只读授权（2026-10-19 Owner 明确批准后的代码增量）

Owner 已明确批准：原平台财务人员经单独授权，可查看、核对指定商户全部门店账单；
门店人员保持本店范围，不增加支付、退款或分账执行权。本增量提供代码及合成测试，
没有给真实账号创建授权。前文“整商户授权设计待明确”由本段更新；提供商全集、日期、
summary、回退及解冻合同缺口不因此关闭。

`MiniApplication.configure_merchant_bills(grants=None)` 仅可在已有原
`provider_actions` 且尚未启动监听时配置，默认空授权。由受保护宿主明确注入
`grants[bill_workspace]`，严格字段为 `finance_workspace`、`user_id`、`project`、
`tenant_id`、`merchant_id`、`sp_mchid`、`sub_mchid`、正整数 `revision` 及唯一
`permission=SUBMERCHANT_ALL_STORES_BILL_READ_RECONCILE`，不接受任意操作列表。
此配置不是公开授权 API，不写原 operations.grants/runtime.bindings 或新 IAM 表。
本地工作台可另配 `merchantBillWorkspace`；浏览器只传 workspace 名称，不能据此
创建/提升权限。原 `providerWorkspace` 的资金操作仍走原路由和原 scope。

新 `/community/merchant-bills` 入口只接受 `bill_fetch`、`bill_rows`、
`bill_reconcile`、`bill_audit`，复用原 Center Web session/cookie 与 CSRF 校验，
不接受 Mini bearer 或混合身份。原 finance_workspace 每请求重新调用原
ProviderActions 授权，须为原 FINANCE_APPROVER/PLATFORM_OWNER，且账号、项目、
tenant/merchant、服务商及特约商户绑定全等；项目 OWNER 或 MERCHANT_ADMIN 本身
不构成平台财务授权。每次请求重新读取显式 grant；删除、改主体/revision、原项目
撤权/到期、账号 epoch 变化、财务 workspace 撤销均拒绝。提供商 I/O 前后、缓存解密、
分页返回与审计写入前后重验冻结上下文，变化拒绝响应并回滚本次投影。

下载沿原签名 GET 票据、固定下载域与 SHA1 完整性检查，保存在原 Center 加密 links。
商户账单 key 明确绑定版本、project/tenant/merchant/sp/sub/kind/date，使用独立
channel；不会将原 store 缓存原地升级。审计也按 bill_key 派生独立 channel，先按本
账单索引分页，再验证内容摘要及 scope，不通过游标、空页或 has_more 暴露其他商户
审计存在性。撤权后旧缓存和审计同样不可读。

已知 TRADE 最小布局及明确特约商户号匹配时才披露白名单财务列；已知 SPLIT 分出
布局须同时匹配分账发起方 sp_mchid 与分账方 sub_mchid。保存前及每次缓存读出均
检查，明示外商户行拒绝。未知布局、不能证明商户归属的行，以及尚无权威方向合同的
回退/解冻行在明细页返回空对象和 `unattributed_rows_redacted` 计数，不泄露其金额、
交易号或参与方；消费者标识、银行卡及下载 token 始终不在财务白名单内。

本地核对集合只来自原提供商 bindings 中同 tenant/merchant/sub 的精确门店三元组，
同 sub 的跨主体绑定冲突失败关闭。用原订单和同 project ACTION 标识将全账单行一次
分配到唯一可证明门店，再复用原核对；重复明细不会跨门店重复累计，未知归属保持
pending。退款记录读取额外限定原 project，不能借同 key 的其他项目记录。原 Center
同事务提供 ACTION/RETURN 证据；六业务库独立连接，不声称跨库原子快照。

输出仅声明 `ALL_CONFIGURED_LOCAL_STORES`，提供商全部来源仍
`NOT_ESTABLISHED`，summary 仍 `NOT_RECONCILED`，Finance 仍 `UNCONFIRMED`，
完整日请求即使零行或本地全匹配也拒绝。核对只保存原业务审计，不核销、不补单、不
重试资金动作。工作台新增门店/整商户选择，并隔离选择代次和分页；403/无效 JSON
清理当前私有结果，迟到旧请求不能擦除新结果或解锁未完成资金操作。

定向测试使用真实原 Center、原订单/加密账本及合成提供商票据；明确禁止 socket
connect/bind，不代表真实授权、生产启用或支付验收。新增跨商户审计分页反例先复现
旧初稿的他商户游标泄漏，再验证独立 channel 下 101 条本账单记录准确分三页，160 条
同项目其他商户记录不影响游标。准确 Hosted 终态另登记 Issue76。

### 消费者原退款恢复与异步选择隔离补修（2026-10-19）

继续核对原消费者流程，确认两类可离线复现的问题。原 `refund_current` 已严格核对
退款记录归属，而指定申请编号的 `refund_application` 和幂等 `refund_apply` 仅核对
payload 的用户/订单，未一致核对 links owner、申请编号、project 和精确门店 scope。
合成原 Center 中修改原记录 scope 或 links owner 后，两入口仍返回记录；修复将三种
读取及新申请的前序指针检查复用同一原归属规则。缺失与损坏记录分别处理，不把异常
指针当作“无申请”，不新增退款资格、金额或审批规则，不改变资金执行路径。

小程序原退款提交/查询、社区列表/关系及订单列表存在 await 后无当前上下文复核：
订单 A 查询期间正常输入订单 B，A 的私有退款意见会写进 B 页面；社区旧响应也可
覆盖新门店关系，旧 finally 可清除新请求等待状态。现请求绑定原 session 实例及代次、
scene、账号、客户项目、页面代次；退款另绑定原订单和选择代次、申请编号及表单，
社区另绑定输入代次，A→B→A 同样拒绝旧响应。成功、错误、结束处理均验证请求归属。

仅本入口的过期只读请求可因选项变化释放其等待状态；已发出的退款申请或社区变更
保持原冻结输入与编号，资金等待也不能被这些输入解锁。卸载后不再发起调用；重复
点击不重复提交，旧请求不能解锁新的资金动作。退款状态必须回显同一订单/申请/账号
及有效版本，异常结果不展示为成功，未知提交保留原申请编号供显式查询。这里只提交
原售后申请，不执行退款；原门店/项目权限和第七批整商户账单授权保持不变。

新增后端反例在准确 d8f4 产品源码先出现 2 例、4 个预期拒绝失败；小程序两条正常
交互反例也先红后绿。定向覆盖补充了真实 mini session 换实例/登出/重登导致的旧响应，
同选择 ABA、表单变更、卸载、旧 finally 与新支付等待隔离。测试禁止真实网络/监听，
不构成真实退款、生产验收或提供商账单完整语义证明。Hosted 精确回执另登记 Issue76。

### 原入驻时间线与同申请号重新补件（2026-10-19）

本增量补齐原 V27 §18.5 的申请编号、版本和时间线，以及审核人、决定、时间、原因、
所依据材料版本的追加留存；原文明确重新提交不能抹掉驳回或补正历史。需求来源为
`DEVELOPMENT_V27_ECOLOGY_V11_20261014.md`，原 Git blob
`82f16f03efd079a90e83cf3b172f5c557e76a206` 的 2524、2526、2528 行。
旧实现只读当前 reviewer_note，补件保存/重提后旧意见不可读，原 history 请求亦不支持；
准确第八批产品的单例先复现此缺失，新增接口后同例通过。

`history` / `review_history` 仍使用原 `/merchant/onboarding`、原 session 与 CSRF，
分别复用申请所有人及既有受保护审核员映射和实时 REVIEWER 角色校验。申请人没有
项目也能读取自己的申请，不由浏览器自行断言角色或其他申请归属。每页按原 owner、
申请编号、revision 先过滤再取 50 条，游标只含本申请 revision，返回前重新核验权限。
没有新增账号、授权表或共享历史池，也不向列表返回 object_id、原件内容或下载地址。

未来工作流动作在原 workflow、元数据和 audit 同一 Center 事务内，把当次说明、
操作账号、前后状态/版本及当时材料版本/审核结论加密追加到原 immutable versions；
保留原 onboarding_events 的摘要和前序摘要作绑定。历史追加失败时，原数据库的状态、事件、元数据和历史同事务回滚，不出现
“状态已改变但该次原因未留存”的成功结果。已有先落盘上传对象在失败后可能遗留
加密未引用文件，不能声称文件系统回滚，不自动删除未知文件；重放仍受原 revision 冲突约束。六个 pinned
Center 文件不变，不新建数据库，不把这份详情冒充原历史摘要的可逆副本。

已有记录仍可复用原 onboarding_events 的版本、事件及账号。只有 application、actor、
revision 和明确操作映射恰好匹配一条原 audit 时才展示其时间，缺失或多条均返回未知。
没有原始详情的旧原因与当次材料关联明确为 `LEGACY_EVENT_ONLY`，不拿当前意见或
当前材料倒填。原上传 versions/objects 提供独立的资料版本档案，能证明上传版本和
账号，不能据此猜测旧审核所依据版本；超过档案显示上限会明确提示未完整显示。

Owner 另明确批准原同号复审规则：已有权限的审核员填写原因，将 REJECTED 申请
以 `REOPEN` 转为原 CORRECTION_REQUIRED；申请人不能自行解锁。必须补改后重提，
并重新逐项审核当前必需材料，才能经独立审核通过。重开不创建新申请号，不删除旧
驳回和材料历史，不自动开通付款。原申请编号/版本和分页时间线已接申请人与审核页面；
重开按钮只在审核页的已驳回状态出现。账号、申请或版本切换清空旧历史；迟到结果、
拒绝响应及非 JSON 错误不能残留旧私有历史或解锁新的请求。

本批新增 18 个后端用例、2 个无监听 DOM 用例，连同 6 个原状态机和 22 个相邻定向
用例通过，覆盖追加回滚、重开与重新审核、权限撤销、51 条分页、旧 audit 唯一性和
页面身份切换。最终定向 Python 运行显式禁止 socket bind/connect。基线复现早期因
测试发现误选，曾额外执行原合成 loopback HTTP 测试，临时监听在其 finally 中关闭；
纠正后的单例红/绿复跑均禁止网络与监听。未启动生产服务或接触真实账号权限及资金。
准确源码摘要、独立复核和 Hosted 终态另登记 Issue76。

### 原 SaaS 履约请求的授权上下文固定（2026-10-19）

继续核对既有 Finance 证明消费与模块履约时，合成反例证明：原代码在 verify 后虽再次
检查操作者，却未比较是否仍为发起请求时的项目/租户。核验期间原 tenant1 权限被撤、
同工作区被受保护宿主替换为合法 tenant2 配置时，仍会兑现或冲正 tenant1 的模块权益。
原地修改 grant 和原项目版本变化也未阻断。四个定向反例先红后绿；测试只操作临时原
Center/订单/模块数据库、合成账号和既有临时签名夹具，不调用实际提供商或 Finance。

现在每个请求固定原账号、项目角色/版本/有效期、tenant/customer、grant、principal 与
精确 scope，以及原 Center/runtime/订单/模块对象、Finance 对象、authority_id 和原价格
映射。再次拥有某项合法权限并不等于仍有本次请求的原授权。verify 前后、Center 预留
前后、每次原订单推进前后、模块权益写入和恢复、冲正，以及私有状态/需求返回时均重验；
改变后拒绝当前请求，不能将旧租户的结果带到新工作区。已存在的 session/CSRF/epoch、
Finance 签名/受众/期限/claim、价格和终态冲突规则继续生效。

`FinanceAuthority.configuration_token()` 是向后兼容的本地只读变更标记，默认 None，
并非授权或 Finance 证明。原内建 SignedFinanceAuthority 额外摘要其公开验证密钥、
允许租户及受众/状态，检测同一实例内部的本地配置改变。已有不透明 adapter 仍验证
对象是否替换；其内部/远端授权状态仍须原 verify 合同负责，不据 None 声称已证明远端
配置未变，不扩大现场 adapter 接入。请求内对象引用与摘要不落数据库，原成功记录、
证明消费键和重启后的幂等/显式恢复格式不变。

各原数据库仍独立提交。如果授权变化发生在原订单或模块提交之后，当前调用拒绝成功，
保留原 RESERVED / REVERSAL_RESERVED 及锁和证据，由之后具有当前原授权的显式请求
按既有事件匹配恢复；不自动重发，不伪称已撤销之前的跨库提交。新增 12 个定向测试
覆盖本地配置变更、预留回滚、部分提交后的拒绝和唯一恢复、私有读取复验；27 个原履约
测试验证签名、重开、双连接竞争及幂等兼容。最终合跑全程禁止 socket bind/connect。
本增量不创建真实 grant、不生成生产凭据、不执行资金动作；精确 Hosted 终态另列 Issue76。

### 入驻申请编号与历史长标识的移动端换行（2026-10-19）

第九批 Hosted 39297970272 的原 Chromium 全流程在 360/768/1440 宽度检查中出现
2 个横向溢出断言失败；该次测试运行 983 项。静态定位发现新增申请编号段落直接显示
`ma_` 加 32 位标识，而原 CSS 仅对 dd 设置长串换行。原两条失败旅程未打开历史列表，
不能把失败归因于已加载的历史材料；历史中的账号、材料长标识同样需要可见换行。

补修只给 `#applicationVersion` 和 `#applicationHistory` 设置最小宽度及
`overflow-wrap:anywhere`，不裁切内容、不隐藏横向溢出，也不修改原 scrollWidth 断言。
新增 Chromium 纯本地 HTML 专项填充完整申请、账号、材料标识和长说明，在三个原
视口宽度检查页面宽度及标识完整可读；它不监听 HTTP 或请求外部页面。当前本地
Playwright 默认浏览器制品缺失，已知系统 Chromium 亦受执行沙箱限制，真实宽度复验
保持未确认，交原 Hosted 环境执行；静态/DOM 检查不冒充浏览器布局通过。

### 原入驻审核结果站内通知接线（2026-10-19）

原 V27 §18.5 第 2522 行要求完整申请、补正、审查、结果通知与再次提交。准确第十
产品的合成申请完成补件审核后，本人原站内通知数量仍为零，通知读取操作也未接通；
两个定向反例先失败，接线后通过。原第十一移动端长标识换行修复完整保留。

整体 CORRECTION、REJECT、APPROVE 和已获批的 REOPEN 现在按申请编号与原工作流
revision，在原审核、历史、audit 同一个 Center 事务内调用已有 notify。继续使用
`COMMUNITY_NOTICE_V1` 的加密记录、去重键与已读标记，不增加通知队列、账号或授权。
通知只给本申请人显示通用结果与版本，私有审核原因、材料及身份资料留在原受保护
详情/时间线；审核通过明确不代表微信支付开通。开始审核及逐份材料过程沿现有进度和
历史显示，不额外发结果通知；旧缺失通知不回填。

原 `/merchant/onboarding` 增加 `notices` 和 `notice_read`，复用原 session、CSRF 及
申请 owner 校验。尚无 CRM 项目的原申请人也能读自己的结果，不借项目或审核员权限
读取他人通知。每页先按原申请/owner/active 精确过滤再取 50 条，游标仅本申请记录；
通知 ID、加密引用、原事件/版本与通用结果均校验，读取及标记已读后再次核验当前权限。
通知写入失败使原数据库中的审核状态、版本历史、audit 和通知同事务回滚，重复旧版本
审核不重复生成通知。已有非事务上传文件限制不由此改变。

申请页新增本申请通知、分页、标为已读及读取申请最新状态。通知可以显示页面表单
版本之后新产生的已确认结果；更新详情仍通过原受保护读取。切换账号、申请或版本会
清理旧列表，迟到读取/已读回包不能覆盖新页面或解除其等待。拒绝、非 JSON、错申请、
错版本引用和错误分页不能伪称已读，错误提示不复制私有响应内容。审核页不借用申请人
通知入口；页面隐藏不是授权依据，服务端仍独立拒绝越权。

新增 11 个原数据库专项和 2 个无监听 DOM 专项，连同 42 个受影响的已有定向用例通过，
共 55 项；最终 UI 增补后重跑 6 个相关 DOM 用例通过。覆盖 51 条分页、无 CRM 项目、
撤权/epoch/CSRF、事务中断、重放、重开后的已读恢复、私有消息绑定和迟到页面响应。
Python 运行明确禁止 bind/connect；不发送邮件、微信或外部消息，真实浏览器布局与
Hosted 全流程状态另列准确回执，不以 DOM 模型宣称实际页面宽度已通过。
