# PR122 客户中心生产准备：国内实查与剩余输入
日期：2026-10-16（北京时间）。原PR122；Work原writer；不新建任务队列。

## 已完成的实际执行
固定root通道已由Owner在原事务准确恢复为GRANTED；真实visudo检查通过。Work实际GitHub调用inspect成功：Run38889575618/Job116935526733。
后续国内运行环境只读检查Run38889936740/Job116936693100成功，production_mutations=0。
Python3.11.6、x86_64、glibc2.38；OpenSSL3.0.12。
系统Python包元数据：cryptography、cffi、pycparser均ABSENT；未将包元数据缺失扩大解释为所有隔离环境均不存在。
工具：clamdscan、clamscan未在PATH找到；systemd-analyze=/usr/bin/systemd-analyze。
xuanjun-customer账号ABSENT。
config.json、runtime.json、INDEPENDENT_REVIEW_TRUST.json、TARGET_ACCEPTANCE.json均ABSENT。
已登记服务名包含provider-neutral-domestic-bridge.service及xuanjun-site-hub-preview.service；只证明unit存在，不证明其业务、身份或渠道API已验收。不读取unit环境或私有凭据。

## 一次性准备顺序及门禁
1. 固定运行账号与准确离线依赖安装方案：运行身份、Python路径、wheel哈希、扫描器版本/病毒库、目录及最小权限、失败/撤销均需明确；现有通道无prepare动作，不能通过inspect偷偷安装。
2. 真实权威映射：Identity/Tenant/Customer/Project/CRM、原订单/合同的实际运行位置、受信导出/调用格式及身份验证。不得用客户自报ID、离线Principal或示例配置替代。
3. 受保护配置：Owner/既有凭据维护方在服务器私有通道注入SMTP、Telegram、飞书、SecretRef、Web AI和加密/备份密钥；不向GitHub、聊天或CI粘贴秘密。复用bridge前先审核准确接口与授权范围，不能因unit同名自动信任。
4. 独审公钥登记：由Owner核实独立保管人并登记root信任；源码作者不产生生产独审私钥或自签批准。
5. 目标证据：按获审安装器既有11类TARGET_ACCEPTANCE绑定以及原规则14项完整验收取得真实结果，R3日志/代理/插桩保密证明不得用合成测试代替。
6. 用同一冻结候选集中独审，取得准确单次安装许可后才运行原apply；完成实机HTTPS/PC手机验收后开放真实资料。

## 当前范围
源码整改与固定通道已完成其获审范围；实际安装前置不齐。许可#6213703300仅批准原通道权限恢复及无副作用inspect，明确不授权依赖安装/客户apply或rollback/凭据接入。
Owner长期开发与操作授权已收到，不再反复要求相同授权；机器门禁仍需准确范围和真实输入。
不得填充示例为真实配置、编造权威服务地址、自动关闭R3或复制新账号/合同/财务权威库。
客服、交易、P2、东京与DNS不受本准备任务修改。

状态：CUSTOMER_INSTALL=HOLD；REAL_CUSTOMER_DATA=NOT_OPEN。该文档是原任务准备清单，不是完成/发布许可。


## 2026-10-17 00:50 北京时间：真实目标机刷新
沿用已批准无副作用inspect，重跑原冻结只读任务Run38889936740，最新Job117088396598 SUCCESS；执行源码6d1a740f90bb870836f92e452ab288da435b82e6，未运行新代码。root仅调用现有固定inspect；其余为Runner非特权元数据检查。production_mutations=0，CUSTOMER_INSTALL_NOT_CALLED。

实际结果：
- config.json/runtime.json/INDEPENDENT_REVIEW_TRUST.json/TARGET_ACCEPTANCE.json：四份均ABSENT。
- xuanjun-customer账户：ABSENT。
- 系统Python元数据cryptography/cffi/pycparser：均ABSENT；不据此断言其他隔离环境不存在。
- clamdscan/clamscan：PATH未发现，不冒称已验证所有潜在扫描服务。
- 既有bridge和网站preview unit仍列出，仅为存在性信息，不表示已验收渠道、密钥或权威映射。
- OpenSSL3.0.12，systemd-analyze可用。

客户整改新源码60d41e5b063d992d4933f8f77544e2c54fda00ca已获#6220298956源码限定通过，前批证据整改继承#6219911538。Hosted77执行77通过0跳过，真实目标机不是这77项的运行环境，不能混写为生产PASS。Artifact12060037405的40成员/39文件为开发方下载核验，独审完整字节复算尚未完成。

原root通道冻结客户包为feaef687ee296dcd55f094bf240fe843445d5ad7。现有GRANTED不是新包安装许可，不能替换candidate后沿用旧制品身份。新包、通道重绑定、独立公钥登记、准确目标机准备动作及回滚须共同形成精确候选，再送同一审核链；不重新审已关闭的轻量整改源码。

当前可复用：已有固定inspect、受保护安装器/回滚逻辑、加密存储、身份与项目权限、轻量整改、签名交付校验和复验组件。
当前仍缺：实际canonical身份/合同来源；实际测试/部署签名交付源；完整私有预览渲染器；自动代码整改执行器；受保护生产配置/独审密钥登记；扫描及恢复/渠道真实验收；新准确安装许可。不能把源码组件当作真实自动整改或生产安装。

普通页面整改不得逐条提升为Owner人工；生产独审密钥保管与生产凭据提供是一次性受保护准备，不等同逐页批准。源码writer不能生成自己的独审私钥并自签生产准入，也不能伪造客户/合同权威来源填补缺失。

此更新仅保存真实只读检查点，不是安装方案已完成、安装许可或上线回执。PR122保持Draft，现网保持不变。


## 2026-10-17 08:04 北京时间后：安装前统一接续（替代旧缺项描述）
本节为本轮准确基线，历史缺失记录保留，不据此声称现在仍全部缺失。
- 源码冻结Commit：bc9404216f2eb69dabf7754950a966238e758596；Tree：4e494d26f7ad94376405bbde85aa98bc00a3d85c。
- 真实私有渲染器、签名交付验证、持久化队列、零模型错字执行原语、候选工件及资源闭包、HTTP→worker→浏览器隔离流程已经实现，不应继续列为“源码不存在”。
- #6226846755关闭错字执行原语源码；#6227041303关闭新增9路径隔离流水线源码。不能扩大为原聚合申请的全部通道、权限、安装组件已获审，亦不构成安装许可。
- CI38983803241：Hosted117250481377，129执行/129通过/零跳过；国内117250938923非root临时验证通过。新候选1440/390浏览器报告通过，明确不是生产HTTPS或生产签名。
- Artifact12082187996：ZIP d03a09d3110cf372d5c6209da4514fffd77f8487c6a36532744e80557ac353d8；TAR 2f155a812f87fd8b9fca238d6dcf343591f0f4c561fdb67675d39d700950818b；Manifest 59050a86d021b736a18c3211fa0101363eb3eee78ceb9a49320d58839564e626。开发方实际下载复算61成员/60项绑定通过；独审完整字节复算未完成，不冒充独审。
- 生成通道SHA f864d40da21544de51cdfcc51998116390dc56afe01dcd17112019a72fbc319a，仍仅4动作、不改sudoers。升级器SHA 9edc15851d653cdbc9366ebc7dcdd8215b2df3814248065fe96d704acbf1111c；未在国内root运行。

### 集中执行准备边界
| 节点 | 已有能力/准确输入 | 尚缺 |
|---|---|---|
| 原通道/新包切换 | stdlib升级器、精确旧包/代码/GRANTED、完整备份/围栏/回滚源码及中断测试 | 原聚合机制独审、完整制品独立下载复算、Owner-root准确只读Plan、Owner私有UPGRADE_TRUST及新的单次批准 |
| 运行环境 | 实际OS/ABI、三份固定wheel、160文件闭包、非root验证 | 专用账户、Root私有路径重建、准确扫描器/病毒库；现有运行builder拒绝root，不能直接复用为Root安装执行器 |
| Worker/私有预览 | 六个unit、凭据隔离、持久化队列、真实隔离测试 | 生产最小publisher配置、独立测试公钥保管及harness、现场隔离/重启恢复/UNKNOWN处理 |
| 权威身份及合同 | 原签名来源校验、租户/客户/项目权限及证据链 | 真实只读来源与合同/订单的受保护映射；另一个ChatGPT分支的新合同文本待原作者审核/交接，不擅自覆写或当生产权威 |
| 正式发布 | 精确计划/独审签名/目标证据门禁和回滚控制器 | 真实配置、12类目标证据及14项验收、单次安装/发布许可、真实HTTPS/手机/回滚验收 |

Root准备执行器及扫描器资产方案并未因运行builder存在而完成。不能先装Worker再回填缺项，也不能把旧GRANTED改包后当新批准。生产凭据与独审私钥须由对应保管方在私有通道提供，不提交GitHub、不让Owner逐页处理普通整改、不让源码作者自签。

### 下一次现场动作的最小允许范围
先对原聚合机制及完整生成通道完成独审，申请仅允许Owner执行升级器plan的只读准入；plan读取固定Root私有输入ZIP、旧通道/旧候选、wrapper/sudoers身份，编译候选但不import、不改GRANTED、不创建运行账户、不安装依赖、不启动unit、不动Nginx/current。原升级器apply/rollback和客户中心apply不包含在这份只读准入内。
输出完整Plan及其规范SHA后，再与环境准备、私有配置和真实目标证据共同绑定新的一次性执行批准；未知或缺失保持HOLD，不能为了完成表格填造私有配置或审批。

新增非root元数据探针只读取固定对象的存在性/owner/mode、账户/OS/工具版本及官网current链接，不读配置正文；PermissionError记UNREADABLE_NOT_ABSENT，不把Runner看不见当不存在。它不验证Root私有grant状态或钥匙内容，真实root状态仍需准确只读Plan。

本文件的文档/探针提交不替换上述bc940421冻结运行源码，不触发业务全量重测，也不签发安装许可。PR122 Draft、生产网站与旧Root通道不变，真实客户资料/密钥入口继续关闭。
