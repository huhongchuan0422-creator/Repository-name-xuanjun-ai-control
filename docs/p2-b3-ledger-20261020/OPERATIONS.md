# B3 canonical ledger：源码交付与实际动作边界

任务：PR17 #6283494928。继承6f2cc6b6，B1/B2/CP03不重装。

## 已实现的真实消费

应用锚点为原`runtime/stage1/ledger_service.py`，增加显式
`--check-isolated-prepared --profile PATH --profile-sha256 SHA`分支。
该分支调用同目录`ledger_prepared.py`，读取原ActivationStore的真实journal链和PREPARED descriptor。
不调用build/listener/transition，不实例化ExecutionLedger，不打开DB、不bind socket。
普通启动继续原load_config/build/listener；原build全部业务语句的AST摘要未变，
新增准备profile拒绝守卫，不允许把准备配置作为启动配置。

原callback UID1004、native/Owner进程身份、ACTIVE及systemd fd3守卫均保留。
UID1002仅准备主体；不把它当所有服务角色，不宣称已经具备root信任、CAP_SYS_PTRACE或socket activation。
完整原runtime源码随Hosted制品提供；新增应用消费分支的三个文件单独绑定SHA。
原B1 release摘要的含义仍是原B1 release，不将候选应用源码伪称为其原Manifest成员。

## 固定配置和路径

固定请求`request.json`为695字节无尾换行，SHA256：
`199938d73d46f5a841cd56f5f51f814256b28bdc5c7cc88d43e3ff07226ee5b9`。
它绑定原CP03 receipt、真实Python binary和三个实际消费源码摘要。
运行时由实际CP03只读生成ledger-config/profile/runtime-invocation/expected-identity，
不得手填旧epoch或改原descriptor的config摘要。

| 资源 | 容器路径/主体 | 权限和用途 |
|---|---|---|
| 原B3根 | `/var/lib/xuanjun-p2-isolated-test/b3-initialize`，UID1002 | 保留0700；不改B1/B2/原10个初始化文件 |
| 原CP03 config/receipt/activation | 原绝对路径 | 分别只读挂载；只读引用，不prepare/reconcile/transition |
| 原`.initialize.lock` | 原B3根内，UID1002 | 只打开既有600文件并flock，不创建另一锁身份 |
| 工具源码 | `/tools/production/p2_install` | 新制品工具只读，不从请求任意加载模块 |
| 真实应用源码 | `/application/stage1` | 原runtime/stage1只读挂载；三文件SHA固定 |
| 新准备输出 | 原B3根下`prepared/`，UID1002 | 首次新建0700；只写本目录，文件0400；O_EXCL pending+os.link不覆盖发布 |
| 原DB/socket预留 | 原`data/ledger.sqlite3`、`run/ledger.sock` | 不创建；若意外存在则HOLD，不unlink或清库 |

候选正常启动argv固定为`/usr/bin/python3.11 -B -S /application/stage1/ledger_service.py --config <新ledger-config.json>`；
cwd固定`/application/stage1`；env仅PATH与PYTHONDONTWRITEBYTECODE；health为499组件已有的process类型，
仅表示进程存活，绝不表示应用协议就绪。准备profile明确禁止实际启动该argv。
本轮实际消费命令附加check/profile参数，仅执行只读配置消费；没有执行服务启动命令。

## CP04–09顺序和恢复

| CP | 必须成立的本次准备判据 | 记录/失败处理 |
|---|---|---|
| 04 | 原CP03完整绑定、PREPARED、预留DB/socket不存在 | 只声称新隔离准备范围，不声称旧实例已停或转换成QUIESCED |
| 05 | 配置/profile/argv发布后，由真实ledger_service检查分支消费并返回绑定摘要 | 部分发布只补缺失项；不同内容HOLD，不改原CP03 |
| 06 | expected身份独立发布，关联consumer/operation/config/profile/UID角色 | observed进程明确NOT_STARTED，PID/peer为空，服务角色未授予权限 |
| 07 | prepared精确路径、0700、实际准备主体访问和逐文件摘要 | 不递归chmod/chown，不把同UID目录隔离当跨角色授权 |
| 08 | 固定独立UID65534的实际OS拒绝探测 | 无setuid能力即UNAVAILABLE，保存不可变观察并HOLD；不消费调用者自称VALIDATED |
| 09 | CP08已有成功终态；TLS由真实消费的摘要配置、精确Unix端点和封闭配置字段派生 | N/A只覆盖本canonical ledger Unix端点，不覆盖整个P2/TLS服务 |

各成功终态以`CPxx-committed.json`不覆盖发布，绑定原请求和前一回执摘要。
缺前置却存在后续终态时HOLD，不能跳阶段。原请求intent固定；换operation/contract不能绕过HOLD。
未知观察另存`CPxx-observation-<sha>.json`，不能覆盖；同一原请求有新真实证明后可新增成功终态，
不把HOLD文件直接改成成功。响应丢失、配置发布后SIGKILL及重开恢复均已定向验证。
`preparation-receipt.json`仅说明准备链，不等于完整B3或服务启动；full_b3_complete始终false。

## 后续现场动作完整清单（本轮全部NOT_EXECUTED）

1. 取得固定Hosted源码制品并按GitHub artifact ZIP摘要核验；解出其tar并验证随包SHA256SUMS。
   在原隔离根下建立唯一新的输入/日志目录，root父目录0700保持不变。
   仅新输入树按工具/应用只读需要布置目录0555、文件0444；不递归修改任何已有目录。
2. 将工具和完整原runtime分别只读挂载到`/tools`、`/application/stage1`。
   原B3根映射到同一绝对路径，原CP03文件/activation再只读覆盖挂载，新prepared为唯一新增输出。
   不挂B1/B2可写目录、生产配置/凭据、共享云权限或Docker Socket。
3. 固定镜像及已测Python3.11.2不重新升级/测量；UID/GID1002:1002、network none、read-only根、
   cap-drop ALL、no-new-privileges、内存/PID/tmpfs约束沿既有批准值。
   execute/inspect/recover必须三个独立容器/进程，均--interactive无TTY，以同请求字节及SHA传stdin。
4. 各动作保留原stdout/stderr、退出状态、容器状态和逐文件摘要；失败不删除prepared、pending或原回执。
   验收看绑定回执与实际文件，不只看退出码。
5. 当前UID1002+cap-drop ALL不能自行变换UID。实际运行会在CP08保留UNAVAILABLE并停止；
   Hosted root测试的独立UID证明不能搬作英国现场证明。
   若需闭合CP08，最小新增现场观察是独立只读主体的实际拒绝探测；不能因此扩大容器能力或伪造root可信输入。
   **外部观察接入及本次现场回执来源尚未冻结，不提供会承诺成功的最终Owner命令。**
   这只阻塞该现场闭环；真实应用选择不再是缺项，不要求Owner重新找应用或旧历史。
6. 原启动后续差异集中保留：正式服务UID/NSS与分组、root-owned激活信任、真实callback UID1004、
   native/Owner身份文件、systemd fd3及原unit能力/文件系统策略。准备profile均未提供这些权限，
   属后续原B4–B7相应边界，不能把本次配置检查当完成或并入P3。

本轮没有英国命令执行，没有DB/WAL/socket/服务/凭据/权限变更。
最终一条正常操作命令仍未冻结，现场次数UNKNOWN；不得将本清单当安装许可或既成事实。
