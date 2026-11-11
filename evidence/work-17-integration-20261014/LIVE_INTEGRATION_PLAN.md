# Work17 真实接线检查点

检查日期：2026-10-14。本文件是接线候选方案，不授予部署权限。

## 已核实的实际入口

- Sites项目：appgprj_6abc848420248191877fcb3d3d33b0d7。
- 自有域名：https://center.wenwenwenyiyiyi.work；域名及SSL均active。
- 平台访问白名单仅一个Owner账号，无编辑者、访客或用户组。
- 原站点源码读取HEAD：16b6113d6d8c98eda8f646437d5ef1f54a9345ba。
- `.openai/hosting.json`只有`static.directory=dist`，当前不是带后端的Worker应用。
- `tools/build_monitor.py`明确显示人工核对快照，未连接实时canonical账本；页面计时不会读取新回执或唤醒模型。
- 原英国Owner dashboard数据API采用服务器受保护Bearer token；其HTML与Sites会话不是同一个认证实现。
- PR72已审实现HEAD a7a3453b5bfb5352d5a5ea85ec2516f0a50495ff，独立审核6162885044，精确Hosted84/84。

## 最小接线顺序

1. 保留原Sites项目、域名、静态资料及单Owner访问策略。准备服务端入口候选，不覆盖资料中心、不新建账号或OAuth体系。
2. 使用原Sites平台服务端认证身份。站点范围内用户ID不等同于访问策略的account ID；通过真实受保护会话确认绑定，不能从客户端字段或邮箱推断。
3. 服务端授权固定Owner后，通过受保护HTTPS后端通道请求英国读接口。英国Bearer凭据仅在服务端secret引用中持有，不放入HTML、URL、浏览器存储或Git。服务访问凭据不等同于浏览者身份。
4. 英国既有controller实际调用PR72 OwnerFoundationController；客户端仅task_id。原connection supplier提供同一canonical只读事务、当前绑定及受保护ActivationStore，原认证源提供验证器。当前尚无已部署handler调用本适配层。
5. 原只读事务读取tasks/spec/checkpoint/fence/epoch；实际producer提供独立认证的完整inventory/records。缺少真实来源时保持HOLD/null。不得借接线创建第二账本、队列或自报验收证据。
6. 成功响应只展示经过限界的七类视图及中文摘要；失败明确显示不可验证，不回退显示旧缓存为实时成功。控制台不得凭视图自动发送、批准、恢复或部署。

## 17项验收映射

|原任务|接线验收证据|
|---|---|
|1 task_cost_projection|实际成本来源、币种和证据；未知保持null|
|2 canary_evidence_coverage|实际目标版本UK回执；fixture不能充数|
|3 dependency_evidence_view|canonical依赖及独立验收摘要；DONE不提升为ACCEPTED|
|4 resume_prerequisite_view|真实当前绑定和重核；视图不授予恢复|
|5 human_alert_payload|原outbox接入和真实送达/ACK另验，不能以payload生成算已送|
|6 run_usage_projection|权威run/provider计量；配额缺失UNKNOWN|
|7 handoff_evidence_view|真实停止/隔离/fence/ACK，而非没有新消息|
|8 cost consumer|controller完整inventory与records来源、版本一致|
|9 usage consumer|真实完整run清单，不能从records反推|
|10 dependency consumer|原tasks全图及有界扫描结果|
|11 resume evidence adapter|可信回执和当前task/spec/checkpoint绑定|
|12 alert adapter|认证回执、允许origin、真实原sender后续验收|
|13 handoff adapter|exact版本停止和交接证明|
|14 canary adapter|精确release/source/artifact/environment|
|15 Chinese Owner summary|真实Owner会话及实际handler调用，7视图中文限界|
|16 snapshot/binding guard|原连接供应方身份/权限、SQLite/WAL路径保护和同事务；路径相同不证明FD/VFS身份|
|17 bounded task scan|真实分页边界、遗漏/不完整明确HOLD|

## 需补齐的具体接口证据

- 原站点尚无服务端handler；需准备保留静态资料的后端候选，并独立审核后发布。
- 实际站点范围Owner用户ID绑定和每任务权限来源尚未取得。
- 英国已部署read handler、原连接供应方配置/运行身份和保护证明尚未取得。
- 实际完整成本/用量producer、独立依赖验收及live送达/ACK/Canary尚未取得。
- UK Python3.6及接线实机验收尚未执行；Hosted源码审核不替代这些证据。
- P2恢复仍由dots负责。不得借本接线启动Runner、旧服务或第二writer。

## 本检查点的动作边界

已只读取原站点源代码并核实配置；未推送原站点、发布、变更DNS/权限/secret或操作英国服务器。
短期站点Git凭据只用于源读取，未保存token到文件。原站点工作区无修改。
