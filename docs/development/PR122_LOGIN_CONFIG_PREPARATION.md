# LOGIN_ONLY 离线配置准备候选

此工具是本地、非生产的准备程序。它不安装服务、不访问SMTP、不调用生产factory/plan、不提供真实密钥生成入口或替换现存密钥，也不出具验收、密钥来源或安装许可。真实秘密只能在Owner自己控制、已获准使用的终端输入；本次开发与测试只使用合成值。

## 支持范围

- `tools/pr122_login_config_prepare.py` 只依赖Python标准库。
- 纯函数`derive_pair`严格验证最小admin schema，从同一已验证对象派生独立runtime对象；`validate_pair`逐字规范编码比较两份共享内容。
- 既有最小admin字段：deployment_profile、keys、active_key、providers、backup_key、backup_key_ref、authority_verify_key。显式首次LOGIN_ONLY形状用initialization_mode=FIRST_LOGIN_ONLY_V1替代authority_verify_key；仅此组合允许无authority，且该字段必须不存在。FULL、无marker旧配置及未知marker均不能借此绕过原策略。profile固定OFFICIAL_LOGIN_ONLY_V1，providers仅smtp。工具不接受可选context/permit或FULL业务，这只是工具范围限制，不改变原生产schema。
- runtime只含deployment_profile、keys、active_key、providers，绝不含backup或authority。所提供数据/backup及适用authority密钥必须是规范Base64 32字节值；首次形状还要求backup与所有data值不同。没有默认随机源或真实生成CLI；纯接口只在显式注入合成熵下测试，不评定实际保管真实性。
- authority_verify_key是canonical exporter使用的HMAC共享秘密，不是独立reviewer公钥。工具通过格式检查不代表取得了正确authority密钥。
- SMTP明确host、port、tls_mode、username、sender、password。port必须真正整数1..65535（纯函数拒绝bool、float和数字字符串）；TTY数字文本先严格校验再转换。tls_mode仅starttls或implicit_tls，不根据端口猜测，不支持明文。
- host接受ASCII DNS名或IP，不查询DNS；username/sender接受现有服务的简单完整邮箱格式。拒绝控制字符和超长值，避免头注入/异常泄漏。不会替邮箱服务证明sender被授权。
- 输入界面一次收集一个既有active data key；纯函数支持现有多key映射。现有CLI仍只处理原既有配置，所有字段均无回显，四类秘密重复确认；不接受秘密参数、环境变量或输入文件，不提供自动读取系统凭据功能。

## CLI和输入

默认无参数仅在内存构造/校验，输出固定脱敏JSON，不写文件。可选`--output`指向现存私有父目录下一个不存在的新目录；真实凭据离线保存动作须另获相应确认。禁止把真实秘密带入AI聊天、云执行器、shell参数或PR。

要求stdin和stdout均为TTY，使用getpass；无TTY、隐藏输入警告、EOF、中断都失败关闭，不退回有回显输入。CLI参数错误、底层异常及中断只输出固定错误代码，不输出输入、路径、原异常、stack trace或两份配置。

所选输出目录必须由Owner确认位于本地可信磁盘；工具不枚举挂载类型，不能替Owner证明其不是网络挂载。工具自身没有任何网络API调用。

Python不能保证清除全部秘密内存副本。工具不能保护同一UID的恶意进程、root、终端录制、受损系统、交换区/备份；Owner必须使用可信终端和本地保管流程。这些不是本工具解决的风险。

## 新目录输出边界

输出功能当前仅Linux且依赖libc.renameat2(RENAME_NOREPLACE)；不支持该原子语义时拒绝，无普通rename覆盖降级。程序拒绝root运行写路径，拒绝/etc、/var、/usr、/run、/proc、/sys、/dev、/root及其子路径，拒绝相对路径、多前导斜杠（包括POSIX特殊的//根）、重复斜杠、点路径段、控制字符、反斜杠及符号链接。所有入口在文件系统I/O前要求规范单斜杠根，不能用//etc等别名绕过。目标父目录必须当前UID所有、精确0700；所有祖先必须root或当前UID所有且无group/other写权限。常见1777 /tmp不符合这个严格策略，不能为了通过而调整其权限，应使用现有私有home目录。

1. 先只读检查输出路径及已存在目标，失败时不提示输入秘密；写入时用目录FD再次检查。
2. 在同一个私有父目录内创建0700临时目录，名字以`.offline-config-incomplete-`开头。UUID只用于目录防碰撞，不是认证密钥。
3. 用O_EXCL/O_NOFOLLOW创建三个0600普通单链接文件：config.json、runtime.json、PREPARATION.json。两个配置包含明文秘密，必须按私密文件保管。PREPARATION仅包含固定离线声明及两文件摘要，不是验收记录/签名。
4. 写循环处理短写，逐文件fsync；读回检查精确文件集合、权限/owner/单链接、稳定元数据、规范JSON、无重复键、完整schema、两文件绑定及receipt摘要，随后目录fsync。
5. 只用原子NOREPLACE发布新目录，绝不覆盖文件、目录或symlink。最后fsync父目录。没有chown、chmod现存对象、账户创建或服务调用。
6. 重命名前失败/中断不会出现最终目录；私有临时残留保留，不删除未知数据。即使里面两个配置已完整，临时目录名也不能通过`inspect_bundle`作为已发布候选。
7. 调用原子发布前即进入“可能已发布”阶段；系统调用成功但Python尚未记录返回时的中断、helper返回后标志赋值前中断，以及发布后父目录fsync失败，均报告PUBLISH_DURABILITY_UNKNOWN。发布阶段清理FD的异常也保持UNKNOWN；CLI一旦进入写调用，未被内部精确分类的返回/输出中断同样按UNKNOWN处理，不误标成输入中断；CLI同时明确输出state=UNKNOWN，不能把可能已发布说成NOT_PREPARED。只有helper明确拒绝或系统调用明确返回失败才可报告已知拒绝；其他发布阶段异常不声称未发布。最终目录可能已存在且内容完整。这是明确的持久性未知，不是成功或可以盲重试/覆盖。断电持久性不能由之后的schema读取证明。

`inspect_bundle`只读显式选择的离线候选，拒绝缺失/额外文件、非0600、symlink/硬链接、重复JSON键、摘要错误、两文件不同或非规范编码。它返回OFFLINE_SCHEMA_VALID/NOT_INSTALLABLE，永远不表示来源真实、已投递、已恢复或已获许可。生产程序不识别这个工具的PREPARATION标记；不能将其当新的生产门禁或绕开原审核。

## 对现有工程的影响

原离线工具交付包含tools下工具、`tests/test_pr122_login_config_prepare.py`和本文及原Hosted的88项测试。本次首装契约增量保留原88项断言，新增22项，精确总数为110；另在原login_release模块新增23项，由既有LOGIN_SCOPE步骤执行。本次只改profile策略与release只读计划的首次分支，不改ops/provider、冻结150项测试集合、100成员限制或已禁用的现场job，不增加触发方式。Hosted要求Python3.11且非root，用审计钩子禁止离线工具测试访问网络/子进程/生产配置路径；所有输入为合成值，失败/跳过/数量偏差均拒绝通过。

新增工具不匹配安装包的scripts/pr122_customer_*.py、tests/test_pr122_customer_*.py及固定docs集合；安装包仍100成员/99文件。原workflow本身在安装包内，因此任何workflow修改都要求重新绑定准确制品。工具、测试、本文及workflow作为制品内独立的`offline-config-preparation/`审阅材料保存，OFFLINE_CONFIG_BINDING.json绑定四文件摘要、准确commit/tree/run和110项测试结果；workflow使用非隐藏制品别名`workflow/pr122-customer-center.yml`并记录源路径映射，避免upload-artifact默认排除隐藏路径；下载回读逐字核对checkout。此离线工具不加入root安装器的payload。

本地测试与独立复审仅覆盖本地合成环境；Hosted结果以对应commit的运行及制品绑定为准。实际目标root-private落盘、长期凭据配置、真实发信、四项验收、独立全范围签名和Owner许可仍由原准入流程单独处理。

## 首次初始化与恢复契约（本地候选）

FIRST_LOGIN_ONLY_V1表示配置创建来源/范围，不表示以后每次备份时目标仍为空。合法首次形状可原样derive/inspect/backup复用，保留原key版本与backup_ref；不要求为此补造authority。运行时投影仍只有原四字段，不含initialization_mode、backup或authority。旧配置不能通过删除authority并贴FIRST完成可信转换：已有/未知目标不允许重新生成或覆盖，原首次安装器仍拒绝已有DATA/CODE/事务/unit等对象。

最小首次分支只适用于原责任方已核实没有需要复用的权威平台账号库。存在既有Identity，即使有人填写“映射已批准”，也不由本候选实施迁移/替换。OS服务账号或home不存在不等于平台Identity库不存在。

首次只读plan还要求原四类TARGET_ACCEPTANCE中的canonical_identity_mapping文件包含精确字段：schema=1、固定target、deployment_profile、initialization_mode、当前manifest_sha256、target_state=ABSENT、identity_decision=NO_EXISTING_AUTHORITATIVE_IDENTITY、observation_ref、observation_sha256、observed_unix。observation_ref限原/var/lib/xuanjun-customer-preflight/内规范路径，经既有root-private、稳定、普通单链接、有界读取核原始hash；记录与来源原始字节必须是严格UTF-8，全部JSON键和值拒绝未配对代理字符及非有限数；不替换或忽略非法字节。来源JSON头subject必须CANONICAL_IDENTITY_INVENTORY，target/time与声明相同。观察必须非未来且最多18000秒，此处只是复用既有常量的保守陈旧拒绝，不扩展许可。

这些是语法/范围/绑定检查，READONLY_PLAN不是事实认证。root自己编造但内部一致的记录不能由schema辨伪；来源真实性与完整性仍须原独审及Owner对准确计划/证据签署。没有对应来源则HOLD，本轮没有实现或声称存在新的现场采集器，不制造验收文件。其余四类真实验收、原计划/源码签名、正式信任、预算、锁/fence和apply前复核全部保留。

纯函数prepare_initial_pair接受上述assessment、观察原始bytes及显式entropy_source；先核scope/时间/原始hash、来源头、ID、计划保管引用和SMTP schema，并对全部非key配置输入做严格UTF-8预序列化及快照，再恰好请求两个32字节值，分别用于data和backup。长度/类型/重复/异常立即拒绝，无重试；从不产生authority或reviewer密钥，不访问文件、数据库、SMTP或网络。该函数无默认CSPRNG，也无任何CLI参数可调用它；本轮仅显式合成熵测试。输出仍NOT_INSTALLABLE，key provenance/custody/recovery未被验证。

实际首次准备需要两阶段：先由原责任窗口取得当前可信身份/目标观察并获Owner对“两类新持久秘密及准确私有保管位置”的动作确认；再用另行准入的受控驱动生成/保存并取得真实保管与恢复证据，之后才形成准确config/runtime和四项验收，走原计划/签名/许可。生成前不能绑定尚不存在的配置摘要，也不能填假恢复PASS。本候选不提供这个实际生成驱动，不声称首装生产准备已闭环。

恢复继续沿原restore-isolated进入maintenance、撤销旧会话/授权且队列UNKNOWN；本轮不增加解除maintenance、导入authority绕过或服务重开路径。真正既有材料只能复用对应keys/ref；未知来源保持HOLD。
