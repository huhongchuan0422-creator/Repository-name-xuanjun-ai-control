# TC477原宿主启动与overlay交接

原installer以现装manifest 15ecfa38228e106dc9b8528e98f5b32e9f7d92e67284c71cc1ab521f22091ac6为before，使用冻结overlay逐文件stage；保留所有未列现装路径，不整树覆盖。本构建工具不安装、不碰服务、current、unit或配置。沿原carrier flock及RESUME/ADOPT/rollback流程串行安装，不另造安装器。

## 实际入口
已有TEST_ONLY命令可不变。若原installer明确选择禁用handoff入口，服务属主0600配置只有：

    {"schema_version":1,"enabled":false}

启动仍用原解释器、原参数，将脚本路径换为 scripts/task_center_handoff_launch.py，加入 --handoff-runtime-config-file <原持方受保护selector文件>。disabled分支原样传递app参数及gateway_runtime/claim/development注入，原测试身份入口保留；handoff为503，不能COMPLETE。原unit必须先inspect后merge，不在文档抄录秘密参数。配置由原installer合法维护，本交付不创建真实配置或切换服务。

启用配置精确字段：schema_version、enabled、tenant_id、issuer、lifecycle_root、ledger_root、namespace、writer、contracts、intake_plans。contracts/intake_plans复用原RoleContractResolver形状，配置不是新授权台账；tenant必须等原--tenant，两root须已存在。只放selector/非秘密策略，不放凭据正文。

受信原宿主代码import task_center_handoff_launch.main，传入已有identity_backend、evidence、gateway_runtime、mcp_claim_host、mcp_development_host、execution_provider（按适用）。没有CLI/env插件导入器，也不把owner grant扩大为三方权限。backend继续使用已审verify/current_session/authorize合同。

启用但CLI没有受信backend：exit69 FORMAL_IDENTITY_BACKEND_UNAVAILABLE，在打开DB、SessionStore初始化或listener之前明确失败；缺root/错tenant在listener前拒绝。这是未启用边界，不是正式backend已部署。

## 8fe同版闭包
依赖锁中的六文件逐字节来自原8fe：backup_component_hostcycle、bridge/v2，以及backup→handoff→source_adapter传递导入。只import不启动job/备份/远端发布/恢复；不包含原1889 job、allowlist或配置。原SOURCE-only prepared assessor仍不能COMPLETE，不能恢复受保护凭据。保留原source_adapter固定来源，不将其旧producer周期冒充handoff周期，也不在构建或验证中调用collect。

## 恢复与未完成
原installer保留原unit/config/current和操作账；回退仅本delta及启动选择，不能把code rollback当DB或外效恢复。正式identity/action持方与receiver/supervisor授权事实、protected recover/reacquire consumer/custodian仍缺；只完成可安装源码/入口闭包，不造正式身份或用合成UNKNOWN冒COMPLETE。
