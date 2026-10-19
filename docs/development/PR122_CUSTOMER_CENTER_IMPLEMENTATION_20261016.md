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

R1实际并发回归另定位UnixStreamServer默认监听队列5不足以吸收8个同时到达的代理连接。生产类CustomerUnixServer固定有界backlog128，保留单进程顺序处理语义；真实Nginx测试直接复用该生产类而非独立放宽测试服务器。首次CI的1个502保留，修订后须重新验证8/8并发请求。

## 2026-10-18 原安装器受控尝试增量（离线候选）

沿用PR122及原固定客户安装事务，不新增任务、账号系统或执行通道。依据既有《DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md》2026-10-18规范，在产品审核基线15c263e、文档基线f328ed上仅增量修改原安装器；原产品未变部分的限定通过可继承，本安装器增量仍须准确CI、完整制品及独立审核，不把旧通过冒称新版本批准。

- 原apply在原网站非阻塞共享锁内，增加固定事务的持久化准入账本；绑定完整许可/评论、plan及其中源码与制品摘要、主机、执行者和有效窗。不同评论、许可或文件名不能重置同一事务预算；已有旧事务一律封存。
- 旧max_executions=1仍仅一次。新明确批准的attempt_policy=CONTROLLED_PREACTIVATION_V1可指定整数2至5；不是自动把旧许可扩成五次。独审签名、Owner受保护信任与准确评论锚、原有效期、配置、运行环境、目标证据、制品和发布门禁全部保留。
- 仅通过原plan/许可准入后才持久消费一次，随后重复核对源码与激活前漂移；准入前失败不算已许可安装执行。进程中断或未分类异常保留UNKNOWN；许可耗尽、变更、过期、成功或已有安装事务均拒绝继续。
- 只允许安装副作用发生前的明确源码/漂移失败，在另一次人工调用时凭原受保护配置中的准确诊断/恢复记录继续；记录绑定前次attempt与相同scope、核验时间和无安装副作用声明。同一诊断重复、旧记录复用、缺失记录均HOLD。记录是受保护操作者声明，不是因果证明；源码不创建记录、不自动恢复或循环重试。
- 本增量不是部分安装后的断点续装。事务创建后，无论部分写入、UNKNOWN或已经rollback，都不清理或重放。已完成步骤不重复；HTTPS smoke成功即结束安装尝试，仍等待原14项真实验收。真实既有失败必须先对账并取得适用恢复范围，不能以本候选解除封存。

本地33个唯一unittest用例通过、0跳过：保留5项原release用例及28项增量，覆盖持久计数/新解释器重启、原锁并发互斥、旧单次、范围漂移、诊断恢复绑定、重复根因、UNKNOWN、部分失败、成功不重放及真实非root/链接/FIFO拒绝。临时文件应用夹具显式适配本地UID1000；不冒称目标root成功路径或服务器测试。新增Hosted测试只在既有Ubuntu隔离job执行；国内self-hosted job保持if:false。原打包器自动纳入新模块/测试，下载回环增加两路径必含断言；完整新Hosted与制品尚待生成验证。

没有服务器命令、部署、账号/权限/凭据变更或真实资金动作。R4/R6旧已消费许可和P2均不变。受保护CRM/项目映射、真实通知/三渠道与AI身份、经批准隐私告知/留存处理引用、扫描器和运行环境、现场对账与安装许可、真实HTTPS/客户验收继续HOLD或未验证；33项离线测试不能替代这些输入。

## 2026-10-18 原安装器 V2 断点恢复增量（离线候选，待独审）

本节补充上一节 V1 的限定实现，不追溯扩大任何旧许可。沿用 PR122、原 `apply`、固定事务目录、同一个 `.attempts.json` 和网站共享 `flock`。新版本必须重新完成准确源码/制品独审，再由既有信任门禁核验明确的 `CONTROLLED_INSTALL_RESUME_V2` 许可。单份许可 `max_executions` 为 1 至 5，覆盖该批准范围的最多五次实际尝试；不是五份许可，也不是五个传输编号。更换评论、文件名、许可正文或重启不能刷新同一事务额度。

明确许可中的 `recovery_actions` 只能选择以下固定动作：
- `REPAIR_INCOMPLETE_OWNED_FILE`：仅在激活前，对持久 ownership checkpoint 已记录的同一 inode，按已批准制品恢复完全相同字节；保留完成文件，修复前核验身份与空间，修复后核验摘要。EINTR/ENOSPC 可进入此固定恢复；不删除其他数据、不任意改配置或源码。
- `RETRY_TRANSIENT_READONLY_CHECK`：仅对固定健康复核的已分类瞬态失败重试；保存失败原因、后续复核动作及验证结果。安装成功的 service/start/reload/enable 和 Nginx 写入步骤不重跑。只读身份/健康复核可再次执行，用于证明恢复时上下文仍一致。
- `RECONCILE_OWNED_CHECKPOINTS`：HOLD 不等于整份许可永久作废。仍有效、同版本、同范围的原许可明确包含此机制时，可验证原账本链、目标/配置/制品、已完成字节和目录身份；无未决副作用或创建意图的目标仍不存在，才把可信对账写回原事务后继续下一次尝试。部分文件只在确有原 ownership checkpoint 时允许固定恢复。现存无归属对象、未知 service 效果、未知 Nginx 替换、冲突和无法证明安全的状态仍 HOLD，不凭猜测重放，也不另造恢复许可。

每次尝试先持久消费额度，再执行安装。原共享锁贯穿循环；每次 lease 绑定原许可有效窗和递增 fence，写入/命令前复查账本及锁 inode。过期、撤销、范围改变、失锁、旧 fence 或账本漂移均停止；旧执行者不能在收尾或对账时覆盖更新的额度。异常记录只含允许的错误类型/返回码/摘要，不保存命令输出或凭据。成功立即终止；第五次失败保留所有失败原因、修复与完成步骤的汇总，不能第六次执行。源码修改不属于原安装许可中的自动修复，必须另走准确版本审核。

独立检查发现并修复了旧 fence 收尾覆写账本、对账期间账本更新和换锁后先消费额度三个问题，专项回归随代码保留。测试均为临时文件和模拟命令，不执行服务器安装、systemctl、Nginx 或真实网络请求；计数以本次独立测试日志为准。既有 33 项 V1/原 release 用例另计，新增 V2 用例不继承重复执行旧 TestCase。Hosted Ubuntu 新增独立测试步骤与制品路径断言，国内 self-hosted job 仍保持 `if:false`。本地闭包构包仅验证文件/摘要完整性，不冒称真实提交的 CI 或现场通过。

账号创建原模块已存在，不重新实现。受保护 root runtime 重建候选属于原准备流程的单独前置条件；客户 `plan/apply` 仍要求账号和 runtime 已经就绪。本增量没有把未核实准备权限、调用者、stdlib/native 闭包或现场证据偷偷接入安装许可。独立审核、有效 Owner 信任/许可、真实环境对账、原 14 项 HTTPS/客户验收仍待完成；离线源码和测试通过不能替代这些外部验收。

本次最终本地结果：69 个唯一 unittest 全部通过、0 跳过，其中原 release/V1 33 项、新 V2 33 项、独立 fence/锁回归 3 项。新增崩溃边界覆盖创建意图已落盘但目标不存在、创建已发生但 ownership 未落盘（拒绝收养）、已记录 WRITING inode 后中断重启，以及文件/账本 fsync 故障。Hosted V2 步骤严格核对 36 项新增用例；最终真实提交 CI 和下载制品仍待运行。

## 2026-10-18：原网站全链统一许可协调增量（非生产候选）

原 `pr122_customer_release.workflow_apply` 内部入口接固定顺序 PROBE → ACCOUNT → RUNTIME → POLICY_RESTORE → CHANNEL_REBIND → CUSTOMER_APPLY。默认固定适配器读取原 CONFIG 下 `WHOLE_WORKFLOW_INPUTS.json`；它只是由原许可逐阶段 SHA256 绑定的数据，不是授权、信任登记或新特权 CLI。原 Owner gate、独立审核、有效期、源码/manifest 和 Hosted CI 校验仍必须通过。V1/V2 许可不会升级为 V3。

新许可显式选择 `CONTROLLED_WHOLE_WEBSITE_V3`，绑定六阶段输入、实现、可继承回执及允许的固定恢复动作，总次数 1–5。原固定 TXN 的同一 attempts 文件保存总额度与逐阶段 intent、成功检查点、原因码、对账证据和恢复记录；换文件、重启、换许可不能刷新已用事务。每次实际尝试共享同一持久 fence；阶段能力绑定具体尝试及未完成 intent，完成或失去 fence 后不得继续写。成功阶段经可信验证后跳过，全部成功停止，第五次失败停止并汇总。UNKNOWN/冲突先 HOLD，只有原有效许可允许且同版本可信证据证明 COMPLETE 或 SAFE_TO_RETRY 才继续，不能把未知写入当作未执行。

实际复用原账号 create_once、原 runtime protected_rebuild、bootstrap 原策略恢复、channel 原固定 writer 和 customer 原 Journal；customer 不另开 Attempts 或内层重试。锁顺序为原网站锁，然后子步骤原 upgrade/channel 非阻塞锁；不允许从已持有子锁的旧 channel apply 反向调用本入口。历史成功只读 probe 必须精确 pin 并继承；不制造第二个 probe writer。账号已有一次性未知 intent 不删除重开，runtime 已有未知部分目录和通道未知部分变更保持 HOLD。精确旧策略恢复仅限新许可明确列出的备份/计划/固定 wrapper 与 sudoers，允许可信已恢复/部分恢复对账；不授权业务回滚。

通道新入口把最终 ZIP SHA256 从统一许可的 artifact_zip_sha256 和阶段输入双重绑定，并校验内部 source commit、manifest、tar、channel binding；旧 CLI 的冻结 pin 保持原样。最终真实 pin 必须在这批源码 Hosted 制品产生后填写，不把此前 apply-only 制品当作全链最终包。打包器补齐嵌套原账号模块 import closure。

本地验证全部为临时目录/依赖 mock，不运行主机账号创建、服务或安全设置变更。新增测试覆盖共享五次额度、重启/并发/fence、成功阶段继承、UNKNOWN 对账、精确策略部分恢复、通道许可绑定、runtime 账户/closure 绑定及借用原 customer 检查点。最终唯一测试计数见冻结交付清单与 Hosted 日志；本地 root-only 原 UpgradeTests 未执行，不能据此宣称现场验收完成。

剩余真实依赖：原受保护调用方接入/授权、新整批 Owner 许可和独立审核、最新 Hosted 制品及准确 ZIP/binding、现场只读 probe 和原账号/策略/通道证据、审核后的完整 stdlib/native/生成 venv closure、准确 wheel 目录及账户身份绑定。缺失或漂移一律拒绝。源码后续修复可以离线完成和测试，但新源码不得用旧许可部署。本增量未执行服务器操作，未证明生产安装、DNS 或业务验收。

V3 独立审核签名额外强制包含 workflow_contract_sha256，并逐字匹配批准的六阶段输入/恢复范围；旧 apply 范围签名不能用于全链，V1/V2 既有签名格式保持不变。

本批最终本地合并专项：195 个唯一测试，195 通过，0 跳过/错误/失败（九个全链模块，不重复计入此前 V2 的69项）。其中真实 Coordinator + OriginalOperations + StageLease 使用临时同一总账，mock 原 writer，验证 runtime 第一次无副作用失败后同许可第二次成功、probe/账号成功不重跑、customer 无内层 Attempts。另两项验证 runtime intent 后失去 fence 不 mkdir、venv 后许可失效不写 vendor 文件。此结果不替代 Hosted 或现场测试。

## 2026-10-18：原入口与不可执行审阅申请

在原 release.main 中补齐固定 workflow-apply / workflow-request 分支；不新增账号、策略、通道或安装 writer。workflow-apply 只读取原 CONFIG 内 WHOLE_WORKFLOW_PLAN.json / WHOLE_WORKFLOW_INPUTS.json，不接受 operations、module、command、自定义账本或配置路径。必须直接 root 身份（uid/euid/gid/egid 均0，SUDO_UID 仅空或0）、原固定主机、root 保护的源码目录和逐字绑定的固定执行模块。JSON 要求 root0600、父链不可非root写、regular 单链接稳定文件、O_NOFOLLOW/O_NONBLOCK、大小和重复键限制。原 sudoers、wrapper、通道命令列表不变，不扩大 githubrunner 权限。

入口验证六阶段输入、静态客户计划、完整 runtime closure 格式与源码；原 workflow_apply 在共享锁内重新读取并核验输入、源 archive、独立签名与 Owner 许可的准确 ZIP，再由原协调器花费同一持久额度。账户或策略动作不能先于制品绑定失败。入口新增源码仍必须经新一轮审核、Hosted 新制品和新准确绑定；e03/7e50 原制品或旧许可不授权该新增入口。

workflow-request 只读本地候选源码与显式 observations JSON，验证 bytes/manifest 后构造六阶段待审 plan、输入摘要与制品关系。缺真实值显示 NOT_EXECUTABLE 与 missing_inputs；即使数据完整仍是 NOT_EXECUTABLE / NOT_GRANTED，不产生签名、批准 comment、nonce 或安装命令，不写入受保护配置或外部服务。模板允许 runtime 的 UID/GID 为 null，仅代表随后从 ACCOUNT 成功检查点派生，绝不预填猜测身份。PROBE 必须继承精确成功回执，不自动 enroll/execute；N1/E1 历史成功保留。

仍需的现场证据分开列明：受保护启动 Python/cryptography 身份，Owner 独立 custody 和完整范围签名/安装批准，真实只读 probe 成功回执，目标 stdlib/native/生成 venv closure，真实 config/runtime/publisher 与12项验收，当前 policy/channel/static plan。已有 wheel/source 和 N1/E1 可按准确证据复用，不要求重跑成功步骤。此处执行入口代码已接线；缺少真实证据时不会生成可执行的假命令。

本批本地验证：62项新增入口/申请专项全通过；与原V1/V2及全链回归合并为326个唯一测试，326通过，0错误/失败/跳过。固定15模块逐项漂移、FIFO非阻塞拒绝、保护父链、四项root身份、锁内ZIP/archive/input不匹配不进入Coordinator均有否定用例。合成包结构检查95成员/94绑定，包含新增模块和测试；该局部结构检查不是新提交制品pin，最终准确绑定等待新Hosted产物。


## 2026-10-18：Hosted 39116357918 暴露的绑定 token 随机碰撞

c69c5841 Hosted 原客户测试在 /bind 输入上被 USE_OAUTH_OR_SECRETREF 拒绝。已用准确基线与确定性合法43字符 token 重现：token_urlsafe(32) 可随机产生 sk- 后接12字母数字的子串，与原安全扫描规则碰撞。这不是仅修测试的随机种子问题。

只将 kind=bind 的生成编码改为 token_hex(32)：保持256位随机性，输出64字符且符合原consume的128上限；其他验证/重置/邀请/确认挑战及session生成不变。safe_text 安全正则、文本入口、哈希保存、TTL、作用域、一次性消费和Web二次确认全部保持。未知真实secret仍拒绝；旧正常URL-safe绑定token仍可消费，旧碰撞token仍拒绝并需重新发起原绑定挑战，不放宽安全检测。

新增确定性回归覆盖碰撞生成、真实secret形态拒绝、subject/channel作用域、expiry、一次性与event幂等、旧普通token兼容、其它challenge编码及未知hex拒绝；原Hosted失败记录保留，修复必须新提交/新CI，不盲重跑旧head。

本批已确认本地10项新增确定性回归与原Customer21项合计31项全部通过；包结构96成员/95绑定，包含新测试，生产未运行。最终Hosted结果另行登记。


## 2026-10-18 官方登录限定部署增量（待独立审核与新制品）

新增明确 `OFFICIAL_LOGIN_ONLY_V1`，默认/旧配置仍 `FULL`，完整模式原五 provider、publisher 与12项 TARGET_ACCEPTANCE 门禁保持。官网静态文件和导航不改。限定模式仅提供注册、邮箱激活、登录、找回/重置、退出及最小本人状态 `/me`；业务API、callbacks、预览、项目/邀请/上传/消息/发布/AI在服务端读取请求体和创建数据对象前拒绝。UI只显示账号已就绪，不显示假项目或已验收业务。

限定配置与 runtime 的 deployment_profile 和 SMTP 配置必须一致，仅允许 SMTP provider。密码/邮箱归属校验、一次性challenge、会话撤销、CSRF/安全cookie、可信Nginx来源、限流、加密密钥与独立审核保管均保留。真实前置为受保护配置、非root身份和隔离runtime、备份材料、真实SMTP；TARGET_ACCEPTANCE精确四项：canonical_identity_mapping、key_backup_recovery、smtp_verified_account_recovery、login_session_security。配置/证据缺失不由fixture或CI替代。

计划和独立Ed25519审核payload新增绑定 deployment_profile、login_acceptance_sha256、permit_window_seconds；限定模式精确18000秒，Owner许可必须同值且 max_executions=5、仍用既有 CONTROLLED_WHOLE_WEBSITE_V3。FULL若明确申请新18000秒窗口亦须在受保护config、计划、Owner许可及独立签名中逐一绑定；无该字段的旧许可仍上限7200秒。复用原交易、共享持久额度、锁/fence、已完成checkpoint、失败对账和成功终止，不增加V4/第二账本。旧已安装单次probe与其1800秒许可不被扩展，PROBE仍要求已有真实成功回执。

安装仅配置center服务、邮件delivery服务与timer，不安装/启动publisher及publication socket/timer。限定worker只发认证邮件；业务CLI在factory/DB前拒绝。原integrity/backup/restore-isolated保留；隔离恢复仍进入maintenance并需fresh authority，不能称无需新授权即可恢复登录。仅借用原受控客户apply阶段，没有新生产许可。

本地新增57项专项（22发布/签名/申请/安装checkpoint、27HTTP、8ops）与既有回归；DOM harness补最小/me模式。原entry fixture增加第16个固定profile模块字节绑定。本地相关376个唯一测试全部通过、0 skip，DOM harness通过。首次误将Hosted以sudo运行的旧ReviewTests纳入非root本地组，产生1个既有root-owner fixture错误，保留日志；未修改或放宽生产root校验，最终376组按非root适用范围执行。Hosted须运行原测试与新增专项并重建新制品。包闭包本地结构100成员/99绑定；本地模拟source ID不是可部署新pin。新提交/Hosted制品/完整许可、现场runtime/config/SMTP/保管与真实验收仍待完成。


## 2026-10-18 W5-R1：耗尽额度与可信只读对账分离

响应原独立审核 #6249284834，仅修整轮协调器的耗尽处理，不修改已通过登录profile、旧probe、许可范围或现有业务。原实现第5次异常直接EXHAUSTED并在重启时拒绝对账；离线故障注入已复现并保留基线失败。

同一原许可、版本、锁和fence仍有效时，第5次失败或重启可走原只读reconcile。全部六阶段均有可信完成证明才写原账本SUCCESS；可信证明明确未完成且额度耗尽则EXHAUSTED；UNKNOWN或对账异常保留HOLD和证据。只允许原账本完成状态收敛，不新增Attempt、stage效果、修复动作或配置写入；第6次效果始终禁止。成功记录继续封存；过期许可、锁替换/fence冲突不得继续写账本。

新增21项故障测试：19项原协调器边界，2项实际临时CUSTOMER_APPLY子回执连接原OriginalOperations.reconcile/child.reconcile/Journal只读验证，覆盖最后真实成功回执丢失返回及KeyboardInterrupt后重启。确认累计仍5次、服务命令不重放；另覆盖UNKNOWN、SAFE_TO_RETRY但未完成、对账异常、expiry/lock/fence及readonly lease拒写。旧39项协调器回归保留，2项旧预期改为允许耗尽后只读重入和UNKNOWN仅状态转HOLD。新增测试追加原已登记模块，Hosted既有whole-workflow步骤自动发现，无新增包成员或派生生成源码。

本地受影响336个唯一测试通过、0 skip；准确记录与新制品绑定以本增量冻结证据/Hosted为准。旧663983制品不能代替修改后新包；本修复不签发生产许可，不补造真实登录验收或现场证据。

## 2026-10-19：SMTP 显式 TLS 模式兼容候选

原传输固定使用 SMTP + STARTTLS，无法直接连接采用隐式 TLS 的465端口。本候选新增受保护 providers.smtp.tls_mode 字段：implicit_tls 使用 SMTP_SSL 和默认465端口；starttls 使用 SMTP、强制 STARTTLS 和默认587端口。旧配置未填写 tls_mode 时继续采用 starttls，不根据端口猜测模式。未知、空值及明文模式在连接前拒绝。

两种模式均使用 ssl.create_default_context() 校验证书链及主机名；只有 TLS 建立成功后才认证并发送。失败后没有应用层重试，不切换SMTP传输协议、不降级明文、不新建连接自动重试，也不自动重投该 outbox 邮件。标准库 smtp.login 的既有行为保持：它可在同一已加密连接内依次尝试服务器声明的多个 AUTH 机制，因此一次 login 调用不保证只发送一次 AUTH。原持久 outbox 在网络动作前标记 UNKNOWN 的机制保持；不确定结果在重新打开数据库后仍不自动重发，ACCEPTED仍只表示SMTP接收，不表示收件箱已送达。

腾讯企业邮箱已确认的465 SSL配置应显式选择 implicit_tls；本说明不写入任何生产配置或凭据，不代表已完成其真实连接或收件验收。config.json 与 runtime.json 的 providers 必须保持完全一致；现有受保护配置、身份、runtime、验收和独立授权门禁不变。新的专用离线SMTP测试另接既有Hosted工作流，保留原150项冻结证据组的成员及断言。候选本地通过不等于Hosted CI、生产部署或邮件投递成功。

## 首次LOGIN_ONLY凭据最小化候选

显式initialization_mode=FIRST_LOGIN_ONLY_V1且deployment_profile=OFFICIAL_LOGIN_ONLY_V1可采用无authority_verify_key的admin形状；FIRST+FULL/未知模式拒绝，旧形状与FULL要求不减。首次计划仍拒绝已有安装对象，并在原canonical_identity_mapping证据中核当前manifest/目标/观察原始hash及NO_EXISTING_AUTHORITATIVE_IDENTITY声明；这是受保护声明的结构/范围/绑定检查，不证明事实。既有Identity需另行真实映射/迁移，UNKNOWN保持HOLD。data及独立backup仍必需，四项真实验收、原独审/Owner签名/预算不变。

离线准备提供仅显式注入合成熵的纯构造接口，无默认随机源、无真实生成CLI；实际首次两类key生成/指定保管仍需单独准入和准确确认。FIRST是创建来源标记，合法原key可复用；不得给未知旧配置重贴标签或覆盖。原restore-isolated的maintenance不解除，本轮不扩大恢复业务。具体边界见PR122_LOGIN_CONFIG_PREPARATION.md。
