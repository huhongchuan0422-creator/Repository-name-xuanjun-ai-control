# PR99 Phase-C：现场准入与执行交接清单

状态：PREPARATION_ONLY / LIVE_EXECUTION_NOT_AUTHORIZED。
独立裁定：https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/99#issuecomment-6212409290
裁定范围：离线源码和候选机制 PASS_WITH_SCOPE_LIMITS；完整 TAR 成员独立复算尚缺。不是安装或运行许可。

## 冻结输入

源码 e9052b4e9d7de8a3cf27b3ab5282a19d120878b4。
Artifact12035120742；ZIP b1ea59d05c8da17ddb037cc4699a75d2b2d5b4f58cf54e7ba0a6e6d2572c43e9。
TAR 898263578775de2d0486f2d2c18986192305a8edbe213279c5c4d7b4e35cc520。
Runtime Manifest dcb5c1810b1ac69d9175ea885dd1816d4f9aa109316db184d96138d8fb296938。
已有开发方真实44绑定/30runtime/45常规成员复算证据供独审核对；不能将开发复算改称独审通过，不重打包不重跑134。
Phase-B #6209166651、R2/R6、17运行文件、原事务及185项审结继承。

## 依赖顺序与真实缺口

| 节点 | 所需准确输入或证据 | 执行边界 / 当前结果 |
|---|---|---|
| C0 制品闭环 | 原独审下载上述准确制品并逐成员复算；沿同一审核申请追加结论 | 仅独审字节证据待补；不重审未变源码 |
| C1 私有身份清单 | 独立只读 SecretRef、实际账号、提供方只读/禁止交易提款证明、整对绑定、期限；分别独立的 broker/source/authority 签名身份 | UNBOUND；私有值不进GitHub/聊天/env/argv，不借用交易master key |
| C2 源真值核对 | 东京准确库身份；获准只读schema核对；算法单/保护单权威来源与现有账号映射 | 实际schema未读；静态13/15不是缺表结论；不造空表或零订单；此节点不默认授权业务记录导出 |
| C3 私有传输及参数 | 双端固定端点/SNI/CA/叶证书指纹、源签名与接收身份；持续collector/receiver投放计划、generation周期；明确观察时长/样本/新鲜度/资源/过期阈值 | UNBOUND；不使用语法fixture或24h旧建议作Owner批准；代码接口不等于现有生产通道 |
| C4 精确执行准入 | C0–C3绑定后的配置/计划及各helper SHA；韩国可信受限root通道、准确有效期/单次许可与私有锚点；东京源端准确数据处理范围另行绑定 | NOT_AUTHORIZED；既有B许可和固定旧helper不可复用；长期授权不产生尚不存在的root通道 |
| C5 停止候选安装 | root_handoff/install_controller准确输入；旧B及共享对象冻结，专用UID和3份不同公钥 | NOT_RUN；新4单元static/disabled inactive PID0；允许的一次daemon-reload须在许可内 |
| C6 内核与进程验证 | fence单次独立动作；双UID×IPv4/IPv6负向DROP计数正增量；PID1实际watchdog/SIGKILL/停止守卫/cgroup证据计划及准确许可 | NOT_RUN；不得仅凭静态unit或超时判通过，不改全局规则、不影响共享对象 |
| C7 私有交付与真实观察 | 经准入的整对临时凭据、持续新鲜WAL闭合代与独立签名验证；实机隔离证明；精确签名窗口及生命周期许可 | NOT_RUN；仅只读GET，无Writer；停止确认后才隔离本轮临时材料，未知保留HOLD |
| C8 汇总裁定 | 同一批准入与真实执行回执、完整观察/异常停止结果 | 只申请新增现场证据裁定；不重复B、未变C源码或CI |
| D/E 生产切换 | 另行权威状态/唯一Writer/回滚/切换许可 | HOLD；C通过仍不授权东京退役 |

以上节点是依赖图，不是要求Owner逐项搬运或逐项提交审核。开发方集中准备准确材料；独审集中补制品字节及部署准入新证据。尚未取得的身份和授权必须明确保留UNBOUND，不生成假值。

C2若需要root读schema，应先取得仅schema/文件身份的受限许可；不能以“核对schema”顺带备份/导出业务行或读取凭据。C6的故障注入必须绑定新C专用服务和次数，不能通过真实交易/断开账号测试。当前源码并未提供一条已获准的C6故障注入通用命令，必须在实际执行计划中另行具体化和审核；不得把它冒充已完成。

## 执行前必须交付的具体材料

- 逐个真实绑定的私有输入清单及准确配置/计划摘要；公开仅存不泄露账号或秘密的安全状态，详细输入保存在可信root私有渠道。
- 明确哪些C动作由已审helper覆盖、哪些仍需准确源端投放/故障验证执行器；缺执行器不能用临时shell替代受审逻辑。
- 每项有副作用动作的准确版本/动作/主机/有效期/max_attempts与失败保留契约；安装、围栏、观察不能互相借许可。
- 一批可执行交接材料需给出真实代码地址/hash/目标、成功终态与失败后保全位置；在这些输入未绑定前不发Owner“先跑看看”的root命令。
- 三个进程资源组、watchdog和跨机持续刷新验收不能由Hosted模型分数代替。

当前可用通道：GitHub仓库与现有非root Runner。当前缺失：C受限root执行与私有托管/源端数据准入；未声称已接通。
生产root安装、围栏、服务启动、真实GET、WAL业务导出、Writer及东京停机均未由本记录执行。官网/current/DNS保持原任务边界。

## 2026-10-16 18:15 Owner-root通道安装增量

独审#6213125007关闭原冻结C制品44/44绑定及30/30runtime独立复算缺口，并批准e3da4ae2固定通道单次安装。以上C0旧待补状态已被本节取代；不重审/重打包原制品。
Owner-root终端回执：FIXED_CHANNEL_READY_NO_PHASE_C_EXECUTION，approval_comment_id=6213125007，phase_c_install_called=false，service_actions=0，retry_allowed=false。这是Owner实机证据，不冒充本窗口直接登录或Runner独立取证。
受限root通道已报告安装；本轮仅通过原v27-readonly-batch队列调用一次固定inspect，验证已装字节和实际sudo入口/缺失输入。无checkout、不调用install、不读计划正文/锚点正文/凭据/数据库，不修改B、网站、DNS或东京。C1–C3真实绑定与C4准确C安装许可仍待完成，C5–C8未执行。
