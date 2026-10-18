# PR122 公开展示与社区手机体验：统一候选及受控发布计划

## 精确继承

公开表达源 e654af3a6a0d59f34b27bbbf8ba3518783c6f719 / 独审 #6217671312 / 静态TAR 6d641401eb9212d3a6745f07bdf9b8a845aaaeb9fbf03542a8b63eafc38a4d19。

社区手机源 790937a5c96afcf3b3660e36cf36cfaab2002a72 / 独审 #6217103876 / 手机TAR c24c657ebb101a1a26b56ed2dcd510c676e02d43c1f9dcfbceed9cd28c166d9f。

两项源码审核继承。公开展示制品独立复算限制由审核方对本次组合实际Artifact补验，不用开发方复算替代独审。

## 本次组合变化

仅添加原审手机包9个文件，逐字节保留；核对原模拟app依赖哈希。中文、英文与默认社区角色选择页的消费者、商家、社区、分账方和平台入口均接同一准确手机版本；英文入口保留现有「角色演示为中文」说明。原测试路径及未接通SaaS入口保留，不启用新支付或后台。

组合清单1,288个公网站点文件，416个overlay文件，原始固定源新增101个路径；459个归档成员，458份包Manifest绑定。对比已审公开展示包，变化仅为9个手机文件、3个角色入口、两个原Manifest、source-pin，以及新增COMPOSITION_MANIFEST；Runtime与发布器字节不变。

新增组合器是离线候选构建工具，无apply、sudo、root安装或生产切换入口。输出明确REVIEW_ONLY。

## 目标基线与只读观察

目标主机 iZvt5t8tlrm8oiZ；当前预期 /var/www/wenwenwenyiyiyi.work/releases/pr122-hub-experience-ca7ab933-r2。

原生产事务 pr122-hub-experience-20261016-r2。当前文件以原b66eba8c静态包的1279文件Manifest核验，不能复用更早1277文件基线。

国内Runner只用githubrunner普通身份读取公开站点、Nginx配置哈希及systemd选定状态；不读取私有密钥、环境或客户资料，不调用客户中心root通道。当前receipt受保护，准确SHA及状态必须由Owner-root只读回执补齐，不通过权限绕过获取。Nginx磁盘源核对不冒充已加载进程验证；Runtime元数据不冒充内核沙箱验证。

## 拟定单次生产事务

拟用事务 pr122-public-mobile-20261016；拟用release pr122-public-mobile-reviewed。仅名称预留，尚无执行许可。

申请正式许可前应冻结：组合准确源码/Tree/CI/Artifact、全部Manifest和制品哈希、当前receipt SHA/current/1279文件基线、Nginx完整源哈希、Runtime验证、受保护发布包装及Host Pins。原发布器固定计数449/1279/92不能直接用于459/1288/101组合包，不得修改已消费许可或盲目调用旧apply。

## 发布与恢复顺序

1. 新包装继承既有受控事务锁、Owner-root路径信任、准确Gate、过期/撤销/单次约束及旧站漂移检查。实现差异绑定当前静态r2回执、数量及本次制品，独审确认后才可执行。
2. 保存1279个旧站文件、两份原CSP元数据及全部实际Nginx源配置，回读逐文件验证，备份hash记入新事务。保留所有r1/r2旧事务和备份。
3. prepare新独立release，不覆盖旧目录；验证1288文件Manifest、CSP及原模拟Runtime身份、沙箱、双会话隔离，不安装/停止/替换Runtime。
4. Nginx只补固定新手机路径，保留原规范URL /about，不开放任意HTML或私有路径；先nginx -t，再作激活前漂移检查，切current与reload。
5. 验收原菜单、双语、ICP、优惠表格、6000→2400→1200、90%/50%、手机角色跳转、两个广告位、旧深链、错误路径、JS/CSP、真实HTTPS与320/390/1440px。
6. 失败或未知结果进入HOLD_PARTIAL，保留现场，不自动重试。仅经同事务批准的rollback恢复旧current与原Nginx，核验旧1279文件及全部配置哈希，保持原Runtime不变；恢复后仍做HTTPS浏览器验证。没有备份验证或发现外部漂移时停止而非猜测恢复。

## 当前禁止项

尚未签发新生产许可；禁止复用已消费的#6216329680等旧许可。客户中心安装、真实客户资料或密钥接收、真实支付、DNS、东京退役、动态展示机制root安装、英国及币安系统均不在本次范围。

## 验证层级

离线组合测试、Hosted真实Nginx、Hosted浏览器、国内普通用户只读观察、Owner-root只读回执、独立制品核验、正式单次许可和生产HTTPS验收分别记录。任何缺失保持PENDING/HOLD。

## Owner-root现场输入已取得（22:42回传）

Owner终端只读回执已归档 evidence/pr122-unified-release/OWNER_ROOT_READONLY.json。准确旧r2 receipt SHA256为2c7507be447676e1cbb6ed649198081850403020c9d1856733b0de0f1eec83a8，状态HTTPS_SMOKE_PASS_AWAIT_BROWSER、intent为空、备份已验证。Nginx测试PASS；master85106执行/usr/sbin/nginx且默认配置命令绑定；内存配置无法直接内省，不伪称可验证。Runtime UID62621/PID269238，BPF直附及有效进出过滤均存在，挂载命名空间独立。此为Owner现场回执，不冒充独审远程登录。

国内普通用户观察CI38916842426/Job117026376801及组合CI38916842527/Job117026379268通过。目标新Host Pins已绑定13个Nginx实际源哈希、旧1279文件Manifest及上述准确receipt，不沿用旧1277基线。

新脚本pr122_site_hub_unified_release.py沿用ca8d2dda既有静态事务包装，保留原冻结helper8c403aac和preflight6b6a8b5f；仅更新新Pins路径、459/458归档与Manifest计数、1288候选/1279旧站/1281备份成员计数、101新增路径、当前体验r2回执路径、独立操作类型PR122_PUBLIC_MOBILE_UNIFIED及组合Manifest绑定。旧发布脚本和旧事务不修改。

新操作类型必须使用新单次许可；原PR122_STATIC_EXPERIENCE和PR122_COMBINED_WEBSITE不能放行。组合制品中的PENDING_ROOT_RECEIPT是先前组合构建时的历史状态；本次发布权威绑定以准确Host Pins及Owner归档证据为准，不更写旧组合包制造相同哈希假象。

发布包装依赖完整旧源包SHA74545480300d8f5ba9b3bd87c6f7e40930eb914e34330923ab4b5a57d6f66e63，仅从原Owner受保护目录复用，不上传私有原始源包。包装不包含许可文件，也不自动部署。


## 2026-10-18：官网静态独立节点与五次受控续接候选

本节为新源码候选，未签发执行许可。以上单次许可、1279历史基线和旧事务记录保持原义，不能因新增代码自动扩大旧许可。

执行原则继承原记录PR122 #6249926385及治理文档提交9261a14591f8ec253dfbab2d49e38b5c5671ba6c。本节只说明官网静态独立节点实现，不另建规则，不绑定注册登录或SMTP，也不改变P2。

静态新profile为OFFICIAL_STATIC_ONLY_V1 / CONTROLLED_STATIC_WEBSITE_V1。复用原Coordinator单一持久账本、最多5次、原transaction.lock、Lease/Fence、已成功阶段检查点。新许可必须准确签名绑定18000秒窗口、源码闭包、静态内容包、当前受保护Host Pins及旧站证据；成功即终止，额度耗尽停止，源码变化须新轮许可。UNKNOWN先HOLD，只有原许可范围内可信只读对账满足安全条件才续接。

完整静态内容仍复用已审核1d02版本1288文件包，不重写其内容。FULL_STATIC_REVIEW_V1显式读取460成员/459绑定；旧格式默认459/458不自动升级。旧站数量从新Host Pins的previous_file_count严格读取；不能把历史1279或目标1288当当前实机观测。路径规范、成员类型、完整Manifest、逐字节哈希均保持强校验。

新的控制器源码另以固定22模块、23成员的REVIEW_ONLY源包交付。STATIC_SOURCE_MANIFEST绑定准确源码提交；其哈希须进入新受保护Host Pins。隔离入口先核验完整源码闭包，再预绑定固定scripts包路径，拒绝影子模块、外部同名包及未绑定缓存。此包不含私有配置、信任库、许可、用户资料或1288静态网页内容。

静态HTTP验收范围仅GET、内容哈希、安全响应头及404。原preview synthetic POST和业务E2E不在本静态profile中运行，业务验收保持PENDING；不能将静态HTTP通过表述为客户流程或生产浏览器验收。

仍需按最终精确候选的本地测试、独立增量审核、新Hosted结果和真实制品绑定分别记录。现场基线、运行时闭包、受保护交付、签名许可及实机浏览器验收未取得者均UNKNOWN，不以本地测试代替。
