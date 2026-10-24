# PR99 最小离线搬迁：当前准确进度（2026-10-16）

沿用原PR99和原分支。Owner决定：旧API暂不重建、不使用；保留已有通道。不得把API建设或真实Shadow作为私有文件搬迁的前提。该范围收敛没有自动授权交易启动、财务操作或东京退役。

## 已实际完成

| 节点 | 真实结果 | 证据边界 |
|---|---|---|
| 韩国原Phase-B安装及兼容收尾 | 原#6209166651通过，继续继承 | 不重新安装、不改17份原文件 |
| 固定root通道 | Owner-root安装，原Runner固定inspect通过 | 只允许固定动作，不代表任意root登录 |
| 东京历史密文异机保全 | 韩国1,320,571,760字节，SHA256 ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 | Owner-root终端回执；不重传 |
| 专用恢复密钥托管 | root私有0600；完整解密流SHA256 1784372b17b3466ad4de946e03fc1a1866abccdab791fc871db08b827757154a | 密钥未公开，完整明文归档未落盘 |
| 选择性历史恢复 | 1373份源码/依赖文件+1份交易库，共66,552,325字节 | 新私有目录；不部署源码或旧API配置 |
| 历史交易库 | SHA256 d0bb23c5cede3a66567373b92221b058aa18e07aa510daf0bc02f8f4770bd0a5，完整性通过 | 历史备份，不是当前最终业务快照 |
| 独立Python依赖环境 | 13项包与东京项目venv版本一致，pip check及一次性无外网namespace导入通过 | 不修改系统/原B环境，不运行交易程序 |
| 两台Runner反采样 | Run38898164991，两Job SUCCESS | UID1001、无sudo/HTTP/凭据/业务库读取；不冒充root私有状态审核 |

韩国新环境：/opt/xuanjun-binance-offline-env-20261016/venv。
历史恢复目录：/root/xuanjun-offline-selected-20261016。
韩国原B仍disabled/inactive/PID0，current仍指向/opt/xuanjun-binance/releases/f887b085508e3ed4。
密文、恢复密钥、业务数据库和私有文件清单不得进入公开GitHub或聊天。

## 尚未完成的真实运行迁移

1. 当前源码/数据的增量时点尚未形成受验收的最终交接。历史恢复目录不能直接替换当前生产；东京现用Portal仍是已通过R4遏制的57e38fc9...版本。
2. Portal、模型/RPC/隧道和旧客户入口仍在东京运行。先明确目标及安全接续，不以“API以后再建”为由默默丢弃通道。
3. 四项财务定时任务仍加载在东京：finance-collection-sync、owner-commercial-ledger-sync、billing-operations-weekly-settlement、billing-operations-weekly-final-invoice。本轮没有操作、停用或迁移它们。
4. root/admin crontab与私有通道配置尚未由本次非root采样读取。不能以该采样宣称全部后台依赖已经清零。
5. 真实应用启用、唯一Writer切换、交易所对账及东京退役均未完成。旧API延后重建，不等于这些生产动作获批。

## 下一执行顺序

- 集中核验已完成的离线保全、恢复和环境实机回执；原B/C及未变制品/测试全部继承。
- 以刚取得的运行职责清单确定增量交接和目标落点，保留既有网站、B候选、共享服务与通道；私有配置只能走私有执行路径。
- 只对明确范围准备必要执行及回滚方案，不启动第二writer，不整包恢复/etc或/home，不自动启用旧脚本/调度。
- 各项实际运行职责完成接续或Owner明确决定保留/停止后，才讨论东京退役。当前必须继续运行。

本轮没有新生产服务动作，没有DNS/官网/current修改，没有交易API或Finance操作。离线资产和环境准备完成，不等于服务器完整业务迁移完成。
