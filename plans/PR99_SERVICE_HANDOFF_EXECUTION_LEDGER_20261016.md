# PR99 剩余服务接续执行顺序与验收账本（2026-10-16）

本表是实际三机采样后的执行准备，不是运行迁移PASS。原PR99原分支继续；API延后重建，不新增API/交易上线前置；不重复已通过资产与环境。

## 本次当前恢复点真实执行（2026-10-16 晚）

Owner在韩国通过sudo-root完成许可#6217030577的一次R2执行，终端返回`CURRENT_OFFLINE_POINT_RECEIVED_PASS`。原1363文件匹配，WAL-aware SQLite恢复副本integrity_check PASS；目标`/root/pr99-current-point-received-v2`。数据库SHA`6d451dfdc4714ca9bc704d719dcb47b02ec1e2ce243f886bfb2578a27fbca232`，密文SHA`2ac42b9e69c69260c99387b2e1ae339dd2e80b3f01c1984858e458e6c8872d32`。这是Owner-root回执支持的真实执行，不是审核窗口直接读取私有原件。原V1失败现场保留；成功R2不得重跑。未冻结Writer、未部署生产、服务动作0、API请求0。R2执行回执已由独审#6217422554限定接受；不升级为独立私有数据库复算。

## 最新原始证据

Run38904470291，提交e4dfdf03a246fd911a226d911970854d2606328e。国内Job116984492029、东京Job116984492318、韩国Job116984492559均SUCCESS。三机UID1002/1001/1001，只读systemd属性和选定监听端口，无checkout、sudo、进程参数、unit内容、私有配置、凭据、数据库或HTTP读取，无服务动作。原20/22/134及既有主机检查全部SKIPPED。

最初workflow e788db355d33d105268c986769317baed8d02f13 / Run38904433601因YAML矩阵表达式未加引号解析失败、jobs=[]，没有主机执行。已在上述准确提交修复；不是重试任何失败生产操作。保留失败记录。

## 十个节点的准确终态

| 节点 | 已有成果 | 尚缺的结束条件 |
|---|---|---|
| S01 任务/目标和旧API范围 | 原PR99、双机固定身份、API延后、旧通道保护已固定 | 不扩大为默认停机权限 |
| S02 异机备份及密钥 | #6215371855限定通过，历史密文与恢复密钥在韩国 | 不重复传输，不冒充当前数据 |
| S03 历史恢复和依赖环境 | 历史1374文件、13项依赖和pip/import验收已通过 | 不重装历史环境 |
| S04 当前源文件身份 | 服务器1363文件19,350,718字节逐文件摘要已取得 | R2已按原服务器摘要复制1363份选定源码；原清单含436份历史backup，不冒充全部当前应用闭包 |
| S05 当前SQLite恢复点 | 原20项继承，R2新增7项通过；#6217030577批准后Owner-root一次执行成功 | 离线恢复点已由#6217422554限定接受（Owner-root证据），不是交易final checkpoint |
| S06 生产目录与运行合同 | 10份unit、1份drop-in及私有元数据已按#6218349901接收；Owner-root成功回执；旧失败现场已保留 | 私有当前配置、运行用户/目录/端口/数据绑定、受控候选与回滚批准；不能整包恢复/etc |
| S07 客户网站动态入口 | 国内静态网站原通过；东京Portal/WeCom仍在运行，国内同名unit不存在 | 国内逐服务接续、真实非写验收、入口上游切换与回滚；不得用历史Portal覆盖R4 |
| S08 模型/RPC/小说/VPN通道 | 三机端口和systemd依赖关系已取得 | 私有配置/证书身份、双端通道与客户端指向验证；UK既有P2由原writer负责，本分支不恢复UK |
| S09 调度与最后增量 | 东京四财务timer实际active；未知root/admin cron已明确登记 | 定时任务保留/迁移/停止的明确决策、私有cron核查、最终数据时点和单Writer安排 |
| S10 正式接续/退役 | 尚未执行 | 全部保留职责已接续或明确取消，验证回滚后再单独批准东京退役；东京继续运行 |

S04/S05本次批准范围内的真实离线复制已完成；不等于1363选定文件覆盖全服务器，也不等于最终Writer数据切换。当前进入S06运行合同与私有通道交接，S07—S10仍未完成。S01—S03已通过历史范围继续继承。

## 服务接续依赖与落点

目标沿既定架构：国内承接网站/客户入口，韩国保留币安离线运行资产与已有小说运行环境，英国开发控制和模型执行由原P2链处理。以下是接续落点，不是已安装声明。

| 职责/当前unit | 本次实证 | 接续顺序与完成证明 |
|---|---|---|
| Portal secure-secrets-portal | 东京active PID3082952，cwd/opt/trading-system；国内同名not-found | 先形成当前源码和必要私有运行材料；国内新隔离候选沿用R4；只读拒绝/健康/上游验证后再修改入口，不停止东京先求测试PASS |
| 客户联系 xuanjun-wecom-customer-contact | 东京active；After包含Portal；国内同名not-found | 国内Portal就绪后接入客户联系；私有身份/回调材料不公开；不以真实客户消息作测试 |
| 客服 xuanjun-wecom-customer-service | 东京active；After包含Portal、provider-neutral-tunnel；Wants provider-neutral-tunnel | 必须核实该精确unit/别名身份，不能把provider-neutral-tokyo-tunnel自动当成同一对象；国内接入后才切回调 |
| 旧小说入口 xuanjun-wecom-novel-ingress | 东京active；Wants korea-novel-model-rpc-tunnel | 韩国已有novel-factory active、cwd/opt/xuanjun-novel-factory/app，不能覆盖该共享实例；保留入口/通道所需内容与回滚，小说功能扩展不加入本批 |
| 国内模型隧道 domestic-model-rpc-tunnel | 东京active；Requires tokyo-restricted-model-executor | 先替代执行端，再改隧道客户端依赖；不能只搬SSH脚本后关闭东京模型端 |
| 韩国小说模型隧道 korea-novel-model-rpc-tunnel | 东京active；After模型执行器；Requires未声明模型执行器 | After仅排序而非存活保证，单独验证上游和失联行为；不以systemd active当端到端PASS |
| provider-neutral-tokyo-tunnel | 东京active；国内bridge active PID188767、cwd既有internal-bridge | 国内18443和19444正在监听，东京19443正在监听；本采样没有证明每个端口的具体PID/流向或认证等价，不从端口号推定已切换 |
| restricted-rpc-openai-shim / tokyo-restricted-model-executor | 东京均active；executor有provider-health-alert.conf drop-in | 私有交接必须包含准确drop-in、身份和运行材料；本次没读内容。与原UK P2 writer明确交接，不能在本分支恢复UK mask或启动第二writer |
| xj-tokyo-vpn | 东京active且Requires docker；docker active | 需要容器/网络/访问端的独立受控接续；韩国tailscaled active仅证明进程存在，不证明VPN用户已迁或可替代东京容器 |
| Binance运行资产 | 韩国B inactive/PID0、PrivateNetwork=yes；当前恢复点R2已接收，S06运行接续未完成 | 本轮只做离线资产，原B和current不改变；未来交易启动另行验证唯一Writer/对账，不能拿API延后当批准 |

后续S06 Owner-root回执已确认韩国443归属morelogin-socks5-permanent.service（gost PID996/root），不得占用、改写或重启该共享服务。19444归属sshd PID1283/UID1000，未证明其具体远端或systemd单元。任何未来部署前必须核实所属者。更多自定义服务、用户级进程、容器和cron尚未穷尽，本次不是完整服务器职责闭包。

## 四项财务调度逐项保留

| timer | 最新状态 | 当前动作 |
|---|---|---|
| finance-collection-sync.timer | loaded/active | 保留东京，不执行或改触发器 |
| owner-commercial-ledger-sync.timer | loaded/active | 保留东京，不执行或改触发器 |
| billing-operations-weekly-settlement.timer | loaded/active | 保留东京，不执行或改触发器 |
| billing-operations-weekly-final-invoice.timer | loaded/active | 保留东京，不执行或改触发器 |

这不是完成财务迁移或Owner已接受丢弃其状态。关闭东京前必须明确处理。韩国已存在的yibi-api、yibi-scheduler、postgresql、redis、morelogin、novel、tailscale均只采样不操作；不为本次搬迁新增易币开发或碰现有共享实例。

## 下一次现场批的必要输入（集中获取，不逐字段找Owner）

1. S04/S05批准复制已成功，提交Owner-root回执做一次执行验收；不重复复制、测试或审核原源码。
2. 独立的私有通道材料采集合同：准确unit及drop-in清单、应用入口/依赖、非API通道身份、双端连接关系、端口所属者、root/admin cron脱敏闭包；敏感材料仅加密私有传递，不入GitHub。
3. 由同一批材料生成国内新候选及明确回滚路径，固定既有Work/current/桥接/共享服务前后快照；不假装本次非root属性是root安装验收。
4. 为实际新安装和上游切换提交一次集中范围裁定。未变的B/C、旧20项测试、官网/HTTPS/R4不再审核。

当前复制许可已消费且成功。本分支仍没有任意root终端，既有固定通道不包含任意私有配置读取或服务切换；不能扩大旧许可。能在当前GitHub通道完成的采样/证据/准备继续推进；需要真实私有数据或服务切换时保留准确阻塞。


## S06 新增实际采样

Run38913529642，提交69eeefabee15fcacc8b0d5deb0fc287898d56b27；三机三个Job全部SUCCESS。完整证据见`evidence/pr99-service-handoff/RUNTIME_METADATA_20261016.json`，下一批边界见`evidence/pr99-service-handoff/S06_PRIVATE_HANDOFF_CONTRACT_20261016.md`。本次确认东京generic provider-neutral-tunnel unit为not-found，不能当作Tokyo命名unit的别名；韩国443归属仍受非root权限限制UNKNOWN，不能盲占。国内site-hub-preview属于其他writer，保护不动。Root/admin cron及其他用户/proc详情仍UNKNOWN，不扩展为root验收。没有服务安装、启动、重启或配置改写。


## R2验收关闭，S06新候选已形成

独审#6217422554已认可R2 Owner-root离线复制回执；S04/S05在该限定证据范围通过，禁止再用#6217030577重跑。下一批S06候选准确源码4c9460a215b793259228f9d2e0fbfe5ea50267a1，Hosted Run38916022943/Job117023586355新增19/19 PASS，原历史测试未重跑，全部生产Runner SKIPPED。候选仅10份unit、1份drop-in及私有运行元数据一次加密交接，不读取EnvironmentFile/Token/SecretRef或数据库，不安装或改变服务。unit原件可能内联认证，全部保持root私有，不可宣称凭据内容绝不存在或上传GitHub。新动作PR99_S06_PRIVATE_RUNTIME_CONTRACT_V1需另行准确许可，原R2许可不能代替。完整API/运行秘密、容器/调度闭包及服务接续仍不冒充完成。


## S06真实私有采集成功（2026-10-16 23:14 Owner消息）

替代许可#6218349901已执行一次，原脚本SHA9ca936d3935732c0b4161f7599286ed63a022a142cb1e6cac69601f64bfb9eca未改。Owner终端报告TOKYO_ROOT_PREFLIGHT=PASS、SOURCE_STAGE=ABSENT、OLD_FAILURE_ATOMICALLY_PRESERVED，随后返回S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS。准确回执见`evidence/pr99-service-handoff/s06-candidate/OWNER_SUCCESS_20261016.json`。原失败目录保存在`/root/pr99-s06-runtime-received-v1.auth-failed-6217834919`，成功材料在原v1接收目录；两个许可均已消费，不再重跑。

10份unit、1份drop-in及1份私有元数据已加密私有接收；archive SHA ec11ca6f579beb681adfd739bfeca5b836a22812676fd86a298340913c5243fd，cipher SHA d9bb83a859e0bfc307890539aa22ed872d9ab51c63db79a63f1e5cbeaa683e06。没有EnvironmentFiles读取、数据库读取、业务API请求或服务操作；unit可能内联认证，原件和密钥不公开。证据是Owner-root执行回执，不是开发方/独审方重新登录后重算私有原件。

韩国443的UNKNOWN已由本次Owner-root采样关闭为MoreLogin gost PID996/UID0；这只解决端口所属者，不等于任何新服务安装可占该端口。19444为sshd PID1283/UID1000，通道端点/认证及最终责任仍需核实。

下一步直接使用已接收材料形成脱敏的运行入口/路径/依赖清单和S07/S08候选，不再采集或重传上述11份配置、不重跑19项测试。已收集配置尚未等于生产迁移：EnvironmentFiles、实际通道身份、容器、root/admin调度、目标目录/账号/端口和回滚仍未闭包；不恢复API、不启动交易、不动Finance或UK/P2。剩余服务落点与受控安装/切换另行准确批准，东京继续运行。


## S06已独立限定验收，现成副本投影已成功

独审#6218862352直接接受#6218740070中的Owner-root执行回执，旧S06采集和19项测试继承，不再重做。Owner随后在韩国执行fbbfc6a7投影，返回RECEIVED_CONTRACT_PLANNING_PROJECTION_PASS；实际公开选定字段见`evidence/pr99-service-handoff/s06-candidate/OWNER_PROJECTION_20261016.json`。本投影不是独审批准的新生产安装，不扩大为服务已迁移。

真实已绑定：18080归Portal，18770/18780/18781归三个企业微信入口，18761归韩国小说SSH隧道，19443归provider-neutral-tokyo-tunnel。十个unit均active/running；EnvironmentFiles均未配置不等于没有内联环境或认证。generic provider-neutral-tunnel仍not-found；现有客服Wants指向该名称，接续候选必须准确处理，不能把两名称当别名。东京443 PID可见但不属固定10unit，不能写成端口无主。

下一批集中解决上个工具未识别的Python模块启动、SSH L/R/D关系、VPN启动方式和入口源码静态依赖。使用已接收S06归档和R2 verified/code，源码按原服务器1363清单逐文件核验，不能用GitHub同名源码替代；不重新采集、不读数据库/密钥/EnvironmentFiles、不执行应用，不安装或启停服务。动态资源/私有材料闭包仍不可由AST推断为PASS。原19/7项不重跑，新批只测本解析器。


## S07 国内独立安装实际超时（2026-10-17 00:45 Owner回执）

Owner在韩国执行准确ae5e03d9安装器，国内root认证后进入源码落盘及独立环境阶段，最终返回`DOMESTIC_STAGE_HOLD_PRESERVE / DEPENDENCY_STEP_TIMEOUT`，协调端返回`REMOTE_INSTALL_FAILED_OR_UNKNOWN_PRESERVE`。本次是实际私有新目录安装尝试；没有得到依赖安装、安装后源码复核或保护对象前后相等的成功回执，不能认定S07完成。准确终端证据已脱敏保存为`evidence/pr99-service-handoff/s07-domestic-stage/OWNER_INSTALL_TIMEOUT_20261017.json`。

保留国内`/opt/xuanjun-migration-s07`、`/var/lib/xuanjun-pr99-s07-stage-v1`及韩国`/root/pr99-s07-domestic-stage-v1`。原安装器的超时处理会终止自己创建的依赖子进程组，原目录和日志不删除、不重跑原安装器。下一步只读核对具体失败日志分类、已装依赖元数据、源码哈希及当前保护状态，再形成有准确前置条件的依赖续接。下载/网络错误尚未从日志确认，不提前归因。未执行unit安装、服务启动或反代切换；东京继续运行。
