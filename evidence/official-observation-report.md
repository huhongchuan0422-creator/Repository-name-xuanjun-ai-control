# 官方受限会话元数据 → TC只读观察候选（作者自测）

## 边界与输入
原已审基线commit `dae7d2ace73b52ce972535d3a00d1c64a810ddde`（父144a），本次不改ledger核心、原TC/其他worktree、线上、业务Writer/lease、调度或权限。main交付的受保护协调产物仅含台账自身作者/独审的两条bounded history；不得上传或复制原文件。读取前后SHA256一致；源按用户确认非客户/密钥数据。证据输出只含本地别名/计数，不含原会话、run、消息ID或受保护路径。

`ApprovedObservationReader`只接受代码内明确批准的collector_ref和main交付的该份**非秘密元数据快照**精确字节摘要，超限或不匹配UNAVAILABLE；不是凭证、签名系统、生产issuer或权限认证，HTTP不能传入源路径。直接调用normalize即使结构正确也标`UNTRUSTED_METADATA_ONLY`、source_observation_verified UNAVAILABLE。仅固定快照匹配后标`MAIN_APPROVED_SNAPSHOT_BYTES_MATCH`，其含义限main协调交付字节相符；官方API issuer、角色实例、Writer及有效权限仍UNAVAILABLE/UNKNOWN。要接后续新快照，须有main或原受保护官方通道提供新的已批准source及可验证绑定，不能自行把任意JSON/GH评论转成可信来源。

严格字段集合和类型，不接body/rawlog/参数/非空tool_calls；对message重复去重，冲突拒绝，session/run与标签交叉混用拒绝；会话、run、消息输出为本地别名，role_ref只是标签非实际身份。只输出工具结果元数据、角色final元数据及API记录时间（不是执行发生时间）；actual_received、worker_started、业务结果/验收、权限、Writer、未决effects、global idle和handoff完成均UNKNOWN。由于来源为有限截断快照，统一标STALE，不用pending 0推空闲或自动恢复。不开dispatch或业务锁。

## 接线与实际结果
观察是单独的只读、非权威source域，不入原ledger events/outbox，不绕开既有enqueue/flush/events/export策略，不改三方完成判定。原admin route `/api/admin/delivery-ledger` 显示自身份观察资料；即使历史台账root未挂载，仍能显示该经main批准快照，并明确ledger_state UNAVAILABLE、task rows 0。原handoff GET只为 `scope=ledger-self-observation` 返回观察材料附件（固定文件名 `xuanjun-observation-evidence.json`）；这是证据导出，不是三方交接完成，也不挂接354业务任务。普通task_id导出原行为不变。页面将观察区与业务任务分开，明确仅台账自身、不代表354业务；无来源时显示UNAVAILABLE。

实际从原 `build_handler` 的 `TaskCenterHandler.do_GET`，不用网络监听，以main实际样本贯通view及scope export；只读、原输入字节未变，记录见 `evidence/official-observation-route-readback.json`：view和export HTTP 200、2个工具结果元数据+2个角色final元数据、STALE、issuer UNAVAILABLE、global idle/Writer/permission/handoff/business UNKNOWN、ledger未挂载、task rows 0、无dispatch。HTTP 200仅限此本地TEST_ONLY观察，不代表线上部署、实时性、独立354状态或业务验收。

`OFFICIAL_SAMPLE_PATH=<main受保护输入> PYTHONPATH=tests python3 -m unittest -v test_official_observation_delta` 6/6（包含实际样本）；直接受影响原route/附件/tenant测试4/4，见 `official-observation-tests.log`、`official-observation-route-regression.log`；node语法和Python compileall通过。有限合成测试包括拒任意JSON/GH评论、body/rawlog/参数/缺字段、重复冲突、角色别名、truncated/STALE、UNKNOWN与过期权限。原bcefb独审已通过的8+4、核心与归档证据按未变范围复用，不重复大构建。

## 原任务未完成
真实354的source/runtime/Writer/申请断点/可信接件及独立监督仍UNKNOWN；浏览器实际交互/小验NOT TESTED。要形成受信实际接件/开始/审核事实，现有 `ExternalReceiptContract.normalize` 仍缺已验证发送/接收角色实例与会话绑定、实际接件和worker start、独立review/accept及当前权限scope/有效期的受保护原系统证明；main现有受限`agents_list`和`sessions_history`若无法提供这些字段，应明确UNAVAILABLE，不能用角色名、时间戳、pending 0或测试verifier代替。未来官方采集至少需非敏感 task_id/attempt_id、受验证角色实例引用、源事件类型和receipt_id、causation、发生/观察时间、来源proofref、当前授权scope/expiry与拒绝事实；缺任何关键项保持UNKNOWN，不要求密码/密钥/原日志。

未部署、监听、加timer、改配置/权限、push或触碰Dots354业务，未取凭据。候选仅本地，作者不自审；请main安排非作者只审本次增量。可保留原资料与源队列，异常停新增观察域，不停原项目。
