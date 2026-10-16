# PR122 客户中心与私有资料：实施与集中验收 V1

唯一任务 PR122，原 Work writer；基础账号、通用权限和存储归玄钧AI实验室自主研发，不归业务项目共创发起人。Owner规则文档5059c9c83ff597698b0f7aaa0ea4f062bb5a3ec3继续有效。官网与动态展示送审版本a772770f未修改；客户中心是另一个准确候选，不继承新版后端独审PASS。

## 真实资产与职责
当前Work分支/所核实main未发现可直接生产复用的通用登录、CRM/Project权限或私有文件运行服务。不能从组件名称推断已部署。复用原community_merchant_contract.valid_id、冻结国内Nginx源码枚举/进程身份核验；旧离线Principal、can_submit、verified_provider契约不是HTTP认证来源，因此不把它们裸露为真实鉴权。使用一个通用账号库，禁止复制到各项目；若现场已有权威Identity，必须先做准确映射和迁移裁定，禁止并行重复账号系统。

ChatGPT源码保持其路径所有权：feature/chatgpt-native-customer-intake-20261016，已读a1337cbaa0dd5cfdbbc4d3df484b8beca54728e3的合同和6类材料教程。教程业务内容/二三级展示仍由ChatGPT维护。本服务通过签署的项目需求清单适配这些字段；缺费用/资格/核验日期等信息显示UNKNOWN/待核实，不生成免费价格或假定资质可用。没有重写其教程或公开收集资料。

Work路径：scripts/pr122_customer_*、tests/test_pr122_customer_*、deploy/pr122-customer-center/**、evidence/pr122-customer-center/**及本实施文档和专属CI。接件#6211789380。没有第二writer、新PR/Issue/任务队列。

## 实现调用链
- 独立同域 /customer/center/ 客户界面，使用原一级架构；不改既有首页/客户项目页面和旧深层URL。仅候选状态，真实URL尚未发布。
- 单个非root服务，受控Unix socket /run/xuanjun-customer-api/http.sock（仅专用身份及Nginx组可连接），经新增精确Nginx prefix转发；Host固定、Origin/CSRF/JSON字段校验，HttpOnly/Secure/SameSite=Strict __Host会话cookie，禁止跨域、URL凭据、缓存/范围下载，接口不记录原始URL/正文/令牌。上传JSON+base64最大7MB、解码附件最大5MB。
- scrypt密码盐+摘要、邮箱核验、短期单次验证/找回，重置撤销全部旧会话/挑战。验证邮件只经TLS SMTP，不能返回验证token给浏览器注册者。缺真实验证通道503；SMTP accepted不冒称收件箱送达。失败登录计数独立持久化，不因认证失败回滚计数。
- 权威关系只从受保护operator导入完整签名快照，revision单调递增、最长24h。绑定canonical Tenant/Customer/原订单/原合同/已核实主体及原签约账号，普通注册不能认领。快照不是财务或合同新账本。导出器/密钥/实际权威路径仍需现场映射；客户端不能调用导入。
- owner邀请EDITOR/VIEWER，挑战绑定已验证目标账号、项目、原owner和有效期，登录后消费；不能邀请自己或降级REVIEWER。独立REVIEWER来自权威快照，不由客户授予。每次材料读写、历史下载、消息和渠道操作重新查询有效项目权限，跨项目/撤权拒绝。
- 材料6状态含IN_REVIEW；每次SAVE/提交/开始审核/补正/通过追加不可覆盖版本，审核CAS版本检查、提交者不能自批。新材料不会改变其他项；ACCEPTED被修改保留accepted_revision及原版本。需求快照保留历史，已移除清单的旧文件仍须授权访问。整体与单项分开，到期显示需要复核。
- 材料按项目/类别区分协议草稿、审核、生效、签署证据、客户材料和内部协议。内部类只允许独立审阅授权访问；不是对客户隐藏按钮。法定主体变更拒绝重用原项目，须新授权项目/合同流程；Owner原始公司名称仍UNVERIFIED，不能因此正式签约。
- 文件在 /var/lib/xuanjun-customer-center/objects，位于Webroot之外。AES-256-GCM，随机nonce、项目+对象AAD、密钥版本；邮箱、需求快照、版本正文、消息和待发令牌也加密。索引为HMAC，密码只存scrypt；SQLite metadata使用最小伪名ID和摘要。密钥在root配置经systemd Credential只读交给非root服务，独立离线备份key，不进入公开制品。密钥映射不是已完成KMS验收。
- PDF/PNG/JPEG类型/体积限制和显式材料类别；clamdscan隔离扫描。任何失败、超时、UNKNOWN不生成可下载对象。扫描临时文件只放服务私有/run目录，结束删除；运行身份、tmpfs、clam数据库/EICAR实机检查未完成。下载attachment/nosniff/no-store，无匿名对象URL。关键词检查仅附加防误传，不能识别任意文档中的所有秘密；项目清单与专用凭据通道仍必要。
- SecretRef/OAuth/SERVER_CHALLENGE只收引用，受控本地Unix元数据服务必须返回精确项目/材料/用途/引用/有效期，校验SO_PEERCRED固定非root UID；缺服务拒绝。这里没有实现第三方OAuth授权、存储客户明文secret，也不能把引用字符串当已验证授权。未知真实socket/身份映射保持未接通。

## 三渠道及供应商边界
网页消息在当前项目事务提交后才回已归档；AI供应商未接入时明确PENDING_PROVIDER，不生成假回复。Telegram只接已配置secret_token的真实TLS回调，私聊from.id=chat.id、非bot、事件时效、只接文本；飞书只接加密签名事件，SHA256(timestamp+nonce+encrypt_key+raw body)、5分钟时效、AES-CBC/PKCS7、token/app_id/事件类型/单聊sender校验。算法参照官方文档及larksuite/oapi-sdk-python core/utils/decryptor.py（Git blob adb188d703d9f61390d8c501ef480056b44de3a1），没有复制其SDK为项目账号系统。

官方参考：https://core.telegram.org/bots/api#setwebhook 、https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/encrypt-key-encryption-configuration-case 。技术字段只在operator配置，不放产品主流程。

网页会话发起短期绑定挑战，绑定具体渠道、渠道主体、项目；供应商验签后原子消费，仍需客户回网页确认真实主体，不能仅靠链接绑定。一个客户同一渠道可授权多个项目，消息必须 /project project-id 正文指定上下文，互不混档。事件去重、同事务归档；失败不回保存成功。撤权/解绑使旧链接失效。

发送先持久化PENDING，网络前写UNKNOWN，成功响应只ACCEPTED+供应商message ID，不冒称DELIVERED；超时/中断保留UNKNOWN，不自动重发。后续对账/真实送达回调适配还未验收，未知不得手改为成功。渠道文件/凭据不采集，引导回专用入口。应用不自动发送开发方测试消息给用户；测试使用注入传输夹具。

## 备份、恢复与删除
对象、SQLite一致性快照、材料历史、账号摘要、权限、审核和链式审计一起备份，TAR整体另用AESGCM备份key加密；备份不含密钥，需映射独立KMS/key_ref和密钥灾备，未映射不得宣称可恢复。受控恢复只写新隔离目录，验证全部成员/hash/AAD/audit/integrity；强制maintenance，撤销所有旧session/挑战/成员/渠道，未发出队列改UNKNOWN。必须导入当前权威授权并经受保护恢复决定后才允许重新开放，防止旧备份复活已撤权成员。原目录及失败现场不覆盖、不删除。

binary rollback不恢复旧DB、不删除客户材料/密钥/备份，先停止本次新增timer/服务，恢复准确原Nginx include，保留证据。任何未知或部分执行HOLD，不盲重跑apply。

保留策略/导出与删除：尚未核定合同、法定保留期和主体，不自动删除已签原件/审核历史。客户可通过项目归档消息提出导出/删除请求，operator核定授权与法定保留冲突后另行受控处理；本候选没有自助批量导出/删除，不将它们列为生产已支持。

## 一次性受控发布与回滚
依赖：Python>=3.11、cryptography==46.0.3、cffi==2.0.0、pycparser==2.23。Hosted下载准确wheel并记录哈希，目标机不能临时pip联网安装或替换系统Python。现有目标Python/依赖实际兼容仍待只读核验；不把英国Python3.6.8要求错误套入新国内运行时。

发行包 CUSTOMER_MANIFEST 绑定完整本地import闭包、三个unit/timer、Nginx候选、UI、测试、规则/实施文档及CI；源码不携带客户信息、密码、key或假正式许可。root安装器plan只读，但本次新后端需要新的实际plan/映射证据，不能继承旧静态r2 plan作为后端验收。

目标前置必须由现有受保护方提供：唯一Identity映射决定、canonical订单/合同/客户/项目导出、独立reviewer权限、非root专用账号、离线已核wheel、root0600 admin/runtime配置、私有密钥与灾备映射、实际clam/SMTP/Telegram/飞书/SecretRef证据。TARGET_ACCEPTANCE.json只绑定真实私有证据路径+SHA与本制品，作者不能填假PASS。当前均无此窗口实机验收，安装器因此HOLD是正确结果。

plan输出含实际Nginx include全集和master启动身份、current、配置hash/UID/私有socket。许可必须绑定plan SHA、CUSTOMER_MANIFEST SHA、准确source_commit及CI，2小时单次、独立审核评论ID及同事务rollback。只安装新隔离代码/服务和一个/customer/center/ include；保留原站current/原Runtime/DNS/东京/P2/Finance。运行后验证真实非root+独立mount namespace，再接Nginx，真实HTTPS HTML字节匹配仅为smoke，终态HTTPS_SMOKE_PASS_AWAIT_14_REAL_ACCEPTANCE。

机器许可格式：PR122可信Owner评论首行 XUANJUN_CUSTOMER_INSTALL，后跟JSON：decision=INSTALL_APPROVED、transaction=pr122-customer-center-install-20261016、plan_sha256、manifest_sha256、source_commit、ci_run_id、review_comment_id、issued_unix、expires_unix、max_executions=1、rollback_approved=true。独审首行XUANJUN_CUSTOMER_REVIEW，JSON含decision=AUDIT_PASS、reviewer_role=INDEPENDENT_AUDITOR、manifest_sha256、source_commit、ci_run_id。源码作者不填写正式许可。

## 14项验收矩阵
规则文档§7逐项保留。源码与隔离测试对应注册/找回/会话、原合同授权/跨项目、分批/并发审核/旧通过版、私有下载/秘密负例、重启、邀请撤销、完整需求字段、供应商签名及UNKNOWN、PC手机、加密备份隔离恢复。Hosted CI仍只能证明隔离测试；真实SMTP邮箱、现场权威数据、真实客户资料、真实三渠道Webhook/送达、KMS灾备、内核隔离、生产TLS/手机及原站回归必须在国内验收，14项生产状态一律NOT_RUN直至现场证据。

服务以专用账号和nginx补充组建立0660 Unix socket，其他本机服务不能抢占TCP端口冒充客户后端；实际Nginx用户必须属于已映射nginx组，否则只读plan HOLD，不临时放宽权限。SIGKILL留下socket时保留现场并停止自动重启成功假象，须受保护核实后恢复，不能盲删socket。

网页AI接线为固定本机Unix网关 /run/xuanjun-customer-ai/reply.sock，校验SO_PEERCRED、完整请求摘要、客户/项目/消息上下文及受保护配置批准的OpenAI model_key。先归档客户消息，网络前持久UNKNOWN；返回后再检查成员权限并归档回复，未知不重试、不假装回答。缺实际网关/身份/模型映射显示待接通，不把国内Qwen运营模型当主客服。测试RPC为夹具，未调用付费模型。

邮箱验证时由邮箱持有人设置激活密码，覆盖预注册密码，防止他人预注册账号后利用持有人验证继承旧密码。主动再次注册未核验邮箱会作限流的新挑战，作废旧验证挑战/未发送邮件；不自动重发UNKNOWN邮件。源码负测覆盖预注册密码不能继续登录。

## PR122#6212557897 集中整改：R1/R2/R3（2026-10-16）

本节取代前文V1安装独审仅靠reviewer_role的校验说明。原独审为CHANGES_REQUIRED，并非发布许可。未改原官网与P2，无目标机操作。

### R1：来源与账号隔离
取消所有客户共享的local-proxy-source键。每个公开认证请求先校验真实Unix socket SO_PEERCRED，仅固定非root nginx UID可提供X-Xuanjun-Client-IP；TCP/其他UID/重复IP头/格式错误/逗号转发链一律拒绝。Nginx从自身$remote_addr覆盖此私有头，并清空Forwarded、XFF、X-Real-IP，客户注入值不能沿用。IPv4映射地址归一，IPv6同/64共享来源配额防隐私地址轮换。持久化事务按来源40/300秒及来源+账号12/300秒限流，原账号级密码/找回限制继续保留。不用一个正常业务全局配额阻断所有客户。

生产默认App拒绝未配置的代理信任；测试边界只能Python宿主注入，不提供HTTP/CLI绕过开关。安装plan核验实际Nginx用户与来源配置；已有real_ip配置不能猜测正确，必须单独验证受信上游映射，本候选对未知real_ip链保持HOLD。Hosted另跑真实隔离Nginx→Unix SO_PEERCRED，多loopback源IP/并发客户端/客户伪造来源头验证，不称生产网络已验收。

### R2：独立身份、不可变版本和完整缺陷终态
GitHub账号和reviewer_role均不再作为独立证明。独审需要Ed25519签名，私钥仅属于Owner核实的独审通道；源码作者及其CI不能持有独审私钥、自动生成生产密钥或登记可信公钥。仓库只有空信任模板及运行时临时测试密钥。

Owner通过原受保护root通道一次性登记 /etc/xuanjun-customer-center/INDEPENDENT_REVIEW_TRUST.json（root0600、父目录root不可被组/其他人写入），明确source_writer_principal、独审principal、公钥、ACTIVE/撤销状态和独立密钥托管核验的证据摘要。独审principal必须不同于writer；没有真实独立托管证明不得登记。此root信任来源是Owner，不是GitHub正文自称、来源分支文件或前端布尔值。没有有效信任或单次Owner锚，机器门禁拒绝；本次未登记任何生产信任或签发批准。

独审评论首行 XUANJUN_CUSTOMER_REVIEW_V2，JSON严格只有reviewer_key_id、payload、signature。签名为Ed25519对payload规范JSON（UTF8、sort_keys、separators逗号冒号、无NaN）的签名，base64标准编码。payload准确字段：
- decision=AUDIT_PASS、reviewer_principal、source_writer_principal；
- source_commit、source_tree、manifest_sha256；
- artifact_id、artifact_zip_sha256、artifact_tar_sha256、ci_run_id；
- scope_sha256 = SHA256(CUSTOMER_MANIFEST.files的规范JSON)，绑定完整文件/摘要范围，未变旧组件可注明继承而不重新审核；
- findings恰好包含R1/R2/R3，每项state=CLOSED及非空evidence_sha256数组；
- issued_unix/expires_unix（最多7天；旧/过期/撤销不能用）。

R3如果只完成源码而现场未核验，可由独审保留SOURCE_FIXED_TARGET_PENDING；但这不是安装可接受的CLOSED。机器门禁要求签名R3闭环证据包含本次plan真实telegram_token_path_confidentiality证据文件摘要。不能由本源码作者把它改为CLOSED。

安装评论仍为XUANJUN_CUSTOMER_INSTALL，但除原字段还必须包含source_tree、scope_sha256、artifact_tar_sha256、artifact_zip_sha256、artifact_id。Owner的root install_anchors按固定事务登记准确安装/独审评论ID与各自完整正文UTF8 SHA256、独立托管证据摘要。任何评论编辑，包括空格变化，都会拒绝；撤销review ID/公钥也拒绝。根信任的公钥/撤销状态摘要进入plan，install_anchors在plan之后登记并逐项校验，不进入plan自身的hash，避免安装正文hash的循环依赖。

门禁核对签名、完整范围、缺陷终态、当前Git不可变commit/tree、成功准确CI，以及真实GitHub artifact ID/digest/head/run且未过期；计划输入还必须携带实际review TAR（源目录父级PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz），逐成员验证与解包源码/Manifest一致。安装许可绑定plan摘要及两小时一次性边界。旧自称角色V1回执一律不能用于新安装。没有默默降级或让CI自动替独审签名的路径。

### R3：Telegram含Token协议路径的隔离
Telegram官方Bot API协议要求Token在服务端请求路径，本候选不伪称可以删除协议字段。改成固定api.telegram.org:443的专用直接HTTPS连接，Token不进入通用urllib URL/request对象，不采用环境HTTP(S)/ALL代理、不跟随跳转，标准TLS证书/主机校验，禁用HTTP wire debug和TLS key log。对外只返回允许的整数message_id；HTTP/JSON/关闭异常均在传输边界丢弃，不保存异常对象/原始供应商响应、不传播带Token的错误或异常链。发送UNKNOWN机制保持。

service/delivery显式UnsetEnvironment代理、SSLKEYLOGFILE及可覆盖CA的SSL_CERT_FILE/SSL_CERT_DIR，LimitCORE=0。凭据仍仅从root配置经systemd Credential注入，不在请求参数/源码/审计/GitHub记录中。测试采用合成Token，覆盖代理环境、调试、keylog、异常/标准traceback/stdout/stderr、跳转、响应反射Token。没有向真实Telegram发送测试消息。

生产仍须证明：进程启动没有URL/局部变量捕获的自动监控/插桩，未启用解密TLS的中间代理、secret路径追踪或核心转储；代理/审计/诊断策略准确无Token，真实配置权限与必要的安全网络连通已验证。普通异常脱敏测试不能证明外部网络/供应商不记录路径。本节新增TARGET_ACCEPTANCE的telegram_token_path_confidentiality真实私有证据绑定，缺失即HOLD。不得把源码整改直接写成生产凭据保密验收PASS。
