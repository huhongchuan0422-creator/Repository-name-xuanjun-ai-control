# PR99 剩余服务接续执行顺序与验收账本（2026-10-16）

本表是实际三机采样后的执行准备，不是运行迁移PASS。原PR99原分支继续；API延后重建，不新增API/交易上线前置；不重复已通过资产与环境。

## 本次当前恢复点真实执行（2026-10-16 晚）

Owner在韩国通过sudo-root完成许可#6217030577的一次R2执行，终端返回`CURRENT_OFFLINE_POINT_RECEIVED_PASS`。原1363文件匹配，WAL-aware SQLite恢复副本integrity_check PASS；目标`/root/pr99-current-point-received-v2`。数据库SHA`6d451dfdc4714ca9bc704d719dcb47b02ec1e2ce243f886bfb2578a27fbca232`，密文SHA`2ac42b9e69c69260c99387b2e1ae339dd2e80b3f01c1984858e458e6c8872d32`。这是Owner-root回执支持的真实执行，不是审核窗口直接读取私有原件。原V1失败现场保留；成功R2不得重跑。未冻结Writer、未部署生产、服务动作0、API请求0。独立实机回执验收待申请，不自批。

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
| S05 当前SQLite恢复点 | 原20项继承，R2新增7项通过；#6217030577批准后Owner-root一次执行成功 | 离线恢复点完整性PASS（Owner-root证据）；待独立验收回执，不是交易final checkpoint |
| S06 生产目录与运行合同 | 三机实际依赖属性已采样；B未启动，所有原共享服务保持 | 私有当前配置、运行用户/目录/端口/数据绑定、受控候选与回滚批准；不能整包恢复/etc |
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

韩国ss出现443监听但nginx.service not-found；不能假定该端口空闲，也不能假设监听进程是Nginx。任何未来部署前必须核实所属者。更多自定义服务、用户级进程、容器和cron尚未穷尽，本次不是完整服务器职责闭包。

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
