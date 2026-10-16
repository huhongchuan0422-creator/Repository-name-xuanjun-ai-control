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
