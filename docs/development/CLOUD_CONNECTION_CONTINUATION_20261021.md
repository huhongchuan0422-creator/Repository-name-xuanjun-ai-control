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
- 英国账户 OSS 控制台实际显示“尚未开通对象存储服务 OSS”，开通后默认按量后付费；未点击开通、未接受协议、未创建 Bucket、未产生采购。

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
| 文件通道 | 真实受控私有后端，私有对象引用返回；严禁公开GitHub正文/base64/Artifacts作为降级 | 英国OSS未开通；暂未选择或新建收费存储，file_sink未接 |
| 网络 | 优先执行器出站，不新增公开root命令端口，不修改DNS、Nginx、TLS或防火墙 | 无改动 |
| 回退 | 停止新连接组件，保留其任务/InvokeId/私有文件/审计；不影响原P2服务和历史 | 待安装器实现；不擅自删除凭据或旧日志 |

英国现有机器凭据与GitHub身份核验授权继续有效，无需重复索取。新增持续任务消费、运行身份委托、私有对象存储及费用不是已完成事项，须在准确对象、代码及策略冻结后一次列齐确认，再安装启用。

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
