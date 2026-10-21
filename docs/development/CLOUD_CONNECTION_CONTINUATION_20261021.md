# 玄钧AI新：长期云端连接接续候选

原任务 PR17。沿用 #6318348766、#6318398283；不另开任务，不激活 P2。

## 实际已完成的身份与连接

英国 root 私有凭据 `/etc/xuanjun-cloud-executor/credentials.json` 已落存并实际调用三台既有 STS 角色。
英国、韩国、国内实例身份查询通过；韩国及国内固定无副作用命令 ExitCode=0，原 InvokeId 文件回传 SHA 匹配。
上述结果继承，不重发原命令。后续独立进程再次取得 STS 会话已经实际执行，但跨真实过期时刻的续期耐久测试、宿主或执行器重启验收未执行。

2026-10-21 本轮新增只读核查：

- 既有 `/etc/xuanjun-development/github-intake-token` 属主为 UID/GID 1003，模式0600，单硬链接。以原属主 xuanjun-dispatcher 使用，没有改权限或复制秘密。
- `/user` 返回200，实际身份332398908 / huhongchuan0422-creator；目标仓库查询返回200。
- 仓库响应中的 permissions 表示该身份的仓库角色，不能据此证明此细粒度凭据具备所有 API scope。尚未以此凭据写评论，也没有部署新后台领取服务。
- 首次核查假定凭据属主root，保护条件拒绝，未读取秘密；查元数据后使用原属主核查。不是更改文件权限后继续。
- 原 `/run/xuanjun-development/broker.sock` 和 ledger.sock 均不存在。不启动旧 P2 或造空账本补齐。
- Owner已明确拒绝开通OSS。本方案不使用OSS、不创建Bucket、不接受开通协议、不产生该项费用。私有文件保管使用现有英国服务器磁盘；远程取件通道须另行实际验收。

## 本次新增源码范围（候选，未部署）

| 路径 | 已实现 | 当前限制 |
|---|---|---|
| production/cloud_connection/queue.py | 准确请求/版本/实例登记，可信数字身份输入，文件SQLite原子领取、项目内排他、持久意图、重启去重、UNKNOWN不重投、原InvokeId终态绑定 | 不替代原项目AuthorityStore、外部Writer/Fence或安装额度账本；不是生产签批 |
| production/cloud_connection/worker.py | 原PR17评论读取适配、编辑/伪造身份拒绝、实际STS/SWAS协议适配、固定只读命令生成、结果身份/nonce/文件SHA验证、私有file_sink接口 | 未接私有文件保管实现、后台循环、回传outbox或服务配置；main明确NOT_ENROLLED，不能称已装好的守护服务 |
| tests/test_cloud_connection_queue.py | 18项有意义回归，含真实文件SQLite、两个连接、独立进程重启 | 本地源码测试，不是Hosted或现场任务闭环 |
| tests/test_cloud_connection_worker.py | 12项网络适配/接收/结果异常模拟 | 模拟集成，不是又新增12项真实云测试 |

本地最终去重后30/30测试通过。先前发现测试模块导入导致重复发现18项，已修正；重复执行不计新增覆盖。HOSTED_CI=NOT_RUN；INDEPENDENT_REVIEW=NOT_RUN。

本候选只登记probe和固定/etc/os-release读取，不接受任意shell、路径、URL、root用户或生产安装任务。
完整运维目标没有缩减为只读：未来具体安装/服务/容器/备份操作须按原业务授权、准确安装包和真实Writer规则接入；该部分当前NOT_IMPLEMENTED，不能用此候选宣称全部运维能力就绪。

## 拟部署对象与一次性改动清单（尚未部署或授权扩大）

| 对象 | 拟定准确范围 | 当前动作 |
|---|---|---|
| 新组件 | xuanjun-cloud-connection，仅机械连接；不运行模型或SDK | 源码候选开发，未安装 |
| 代码 | /opt/xuanjun-cloud-connection/releases/<准确审核版本>/ | 未创建；待完整实现和审核冻结版本 |
| 配置 | /etc/xuanjun-cloud-executor/connection.json、targets.json | 未创建；已有credentials.json保留 |
| 状态 | /var/lib/xuanjun-cloud-connection/queue.sqlite、private-results/ | 未创建；与原development/P2账本完全分开 |
| 服务 | /etc/systemd/system/xuanjun-cloud-connection.service | 未创建；运行身份/凭据读取委托须最终冻结后确认，不擅改sudo或账号 |
| 任务入口 | 原PR17 XJ_CLOUD_TASK_V1封套，读取API真实数字身份；不触发Actions | 适配函数已实现，尚无常驻领取者或真实提交/领取验收 |
| 文件通道 | 真实受控私有后端，私有对象引用返回；严禁公开GitHub正文/base64/Artifacts作为降级 | 不使用OSS；服务器私有磁盘保管已实现候选，向调用窗口交付仍未接通 |
| 网络 | 优先执行器出站，不新增公开root命令端口，不修改DNS、Nginx、TLS或防火墙 | 无改动 |
| 回退 | 停止新连接组件，保留其任务/InvokeId/私有文件/审计；不影响原P2服务和历史 | 待安装器实现；不擅自删除凭据或旧日志 |

英国现有机器凭据与GitHub身份核验授权继续有效，无需重复索取。新增持续任务消费、运行身份委托、私有文件远程交付不是已完成事项，须在准确对象、代码及策略冻结后一次列齐确认，再安装启用。

## 完整验收表

- 三台既有角色/实例：已实测。
- 有限云命令和小文件SHA：已实测/继承已实测，原InvokeId不重放。
- 队列去重、双连接、进程重启：本地源码测试已通过；现场守护进程重启NOT_EXECUTED。
- 当前开发窗口真实提交→服务器领取→执行→回传：NOT_EXECUTED。
- 第二真实开发窗口同机制调用：NOT_EXECUTED；不能用第二GitHub账户或模拟进程冒充第二窗口。
- 通用私有文件传输到调用窗口：NOT_IMPLEMENTED/NOT_VERIFIED。
- 真实身份过期后的续期耐久测试：NOT_EXECUTED。
- 常驻服务、完整运维操作注册、结果回传outbox、告警及磁盘预算：NOT_IMPLEMENTED。
- B5/SDK/官网/社区/采购：NOT_EXECUTED。

新服务器必须登记账号、产品、地域、实例ID、主机、用途、角色与真实授权后才纳管。客户第三方账号不能从三台现有信任推定授权。
采购沿原有效订单、对应足额预存款、明确规格/期限/含税及必选费用≤10000元等规则；本连接任务没有采购指令。


## 继续实施增量：无OSS常驻入口候选

新增runtime.py、运行时回归、独立systemd单元及仅GitHub托管离线CI工作流。
这些均未安装到服务器，未启动服务；不能把源文件存在当作现场闭环。

- runtime.py已实现持续领取、持久游标、单实例flock、原InvokeId对账、持久回传outbox、信号停止。
- 发送结果前持久POSTING；响应未知转UNKNOWN，重启不重复POST。云执行意图未知不重发。
- 私有文件固定保管在英国服务器private-results，逐级目录描述符/no-follow、0600、SHA、配额、原子无覆盖发布及幂等校验；没有公开GitHub文件降级。
- 公开回执仅返回request ID、状态、InvokeId；文件明确NOT_DELIVERED，不能误标已到调用窗口。
- 本地最终43项去重测试PASS，新增13项。此前30项包含于43，不累加计数。
- 本轮现场只读核实英国Python3.6.8、SQLite3.26.0、systemd239；候选兼容性Hosted结果需按准确提交另记。
- 英国有SFTP，但当前Work容器无现成SSH身份且原网络实测不通22端口；未导出云密钥给其他窗口。
- 127.0.0.1:28443是既有客户服务的SSH转发，不是本任务私有文件接口；未调用/改动该服务。
- 已检索可用集成，当前返回的结果中没有适用阿里云/SSH/SFTP连接器，不能据此断言全目录永远没有。

### 待落地的准确安全变更

常驻只读接线服务拟使用现有root身份读取既有云凭据及UID1003保管的GitHub intake凭据，不复制秘密、不新建账号、不新增AccessKey、不打开监听端口。
新委托的持续能力仅限固定三机admin probe和/etc/os-release读取；不接受任意命令、sudo、安装、服务启停或采购。
拟启用xuanjun-cloud-connection.service，代码根/配置/状态路径沿上表；新unit与旧dispatcher/P2隔离。
unit仅保留CAP_DAC_READ_SEARCH以读取原UID1003私有凭据，开启NoNewPrivileges/ProtectSystem/ProtectHome等保护。
该新常驻委托与运行候选须在准确版本冻结后，按适用操作确认规则实施；本批未实施。
回退为停止/禁用此新服务并保留其SQLite、InvokeId及私有对象，不删除现场，不触碰其他项目服务。

### 不可省略的剩余验收

1. 准确候选Hosted CI及正常审核；实际安装、自动领取、出站回传与重启恢复。
2. 私有文件从服务器到调用窗口的认证传输，不以服务器磁盘保管代替完成交付。
3. 第二个真实开发窗口提交/查询实测，不能借第二账户或模拟进程冒充。
4. 跨真实STS到期时刻续期耐久测试。
5. 完整运维操作按真实业务授权注册；连接组件不能自动批准P2、官网或资金写入。

OVERALL_ACCEPTANCE=INCOMPLETE。B5/SDK/生产部署/采购均NOT_EXECUTED。


## 冻结前部署入口与CI修复

部署入口deployment/cloud-connection/enroll.py默认只做plan；仅--apply才创建新服务对象。
其运行源码固定f3bfc3fe531c7dcbaa4d94bb8ef52b83e3f02565，逐文件绑定queue/worker/runtime/unit四个SHA；不取浮动分支。
任何既有目标对象/部分安装均HOLD，不覆盖、不盲重启，不触及旧P2。
新增6项enrollment负向/模拟测试，最终本地49项通过（43已包含于49）。

首轮Hosted 39621957992：Python3.6.15的43项通过；Python3.12因容器Git目录属主检查在测试前退出，不能写双版本全PASS。
修复只为准确已检出workspace按命令指定safe.directory，继续强制git HEAD等于GITHUB_SHA，并保留真实Git Tree/Parent日志；不使用||true忽略版本检查，不降低测试。
新版Hosted以最终提交回执为准。所有Hosted均为GitHub托管离线容器，无self-hosted、云秘密或服务器命令。
