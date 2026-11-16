# 144a + ledger 隔离整合（作者自测，未发布）

## 真实基线与保留范围
- 原始task-center repo之clean worktree `workspace-developer/deliveries/github-code-sync-20261115/tc-reviewed-a55c-worktree`，branch `candidate/tc-workbench-resources-20261115`；基线完整commit `144a5387cdbed0f0e30354edbc95d62522e3b803`、tree `2998aa38c57dc8440bd4416151acec3e5de4ac0f`，开始时clean。app SHA256 `bf261045015ee72f4314f80609709d611a5564bb13262b5ecc42df7f95d3c78d`，admin HTML SHA256 `e1c58ca6e81de6f5090ccbeb3ca3a3640108de7d964009981e61a33aedcc2f49`。main实核关联原writer/reviewer均final/pending0；这不是原共享lease，也不证明原业务effects已结清。
- 本目录通过本机shared对象库克隆完整144a，无网络，建立独立worktree和本地commit；初始tree与144a完全一致，产物父提交应精确144a。来源 `integration-tc-7d5408` @89c43df与其patch均原样保留；对7d patch做3-way check发现app冲突，没有用7d整文件覆盖。手工只复制新增模块与逐行合入路由及一条admin链接；保留144a的a55c后继、749579公共同一快照及144a workbench，原dirty app.js和原共享树未动。本地隔离候选不是原commit，也不是线上安装。
- 容量：clone前df可用14889811968字节，后14827302912，现场差约62509056字节（共享系统并发仅瞬时观察）；候选体积约60 MiB；未安装依赖，未触生产。

## 修复与真实限制
1. ledger reader配置需与handler tenant一致，启用reader时SessionStore.tenant_id需相同；新ledger/page路由再核session实际tenant和admin角色。组装错租户fail closed；缺会话/非admin/过期/错误Host拒绝。只约束新路由，不改变原`_admin_allowed`或legacy route。原review probe在本candidate源码实际执行后组装抛`TEST_METADATA_SESSION_TENANT_MISMATCH`，故原probe后半段不再执行；完整结果见 `reviewer-probe.log`。
2. GET handoff由原 `_send` 发送固定 `Content-Disposition: attachment; filename="xuanjun-task-handoff.json"`，继承`Cache-Control: no-store`与`X-Content-Type-Options: nosniff`；对原handler真实`_send`做无网络断言和去敏合成结果校验。无任意文件名注入。
3. ledger core由已审edd引入，SHA256 `031dbefba6168648579c27fd29c8c5dd1fe0622ef2d642a4019924c894bbd623`，未修改；reader默认无接入=503，observer默认UNAVAILABLE，source/writer信任UNKNOWN。原TEST_ONLY receipt contract不能冒可信生产回执；MANUAL_REDACTED与有限模式不是认证或全面脱敏证明。三方缺监督不完成。历史354示例只历史，当前354 source/runtime/writer/申请断点仍UNKNOWN。

## 执行证据及未完成
- `PYTHONPATH=tests python3 -m unittest -v test_delivery_144a_delta test_delivery_ledger_route` 8/8：实际 `build_handler`/`TaskCenterHandler.do_GET`、原SessionStore与临时SQLite，无socket；含原API、Host、无会话、非admin、过期、跨tenant store/返回session、reader错tenant、损坏文件、历史354、handoff和三方未完成。`evidence/integration-tests.log`。
- `PYTHONPATH=tests python3 -m unittest -v test_public_snapshot_consistency_delta.PublicSnapshotConsistency.test_concurrent_wal_writer_cannot_mix_counts_and_source_time test_public_snapshot_consistency_delta.PublicSnapshotConsistency.test_public_read_does_not_change_database_or_wal test_public_projection_metadata_delta` 4/4，临时SQLite验证原公共snapshot与metadata；不监听，`evidence/snapshot-regression.log`。同一handler直接核144a五个research-workbench资源原hash及public projection，原`/api/projection`、`/`、Host旧路径；JS `node --check`、Python compileall通过。未重复原ledger长测或完整build。
- 浏览器渲染/交互、小验、实际安装和真实运行均NOT TESTED；当前真实角色/权限、Writer、receipt验证器与TC hook仍未接，不以合成会话和200冒真实验收。现有`ExternalReceiptContract.normalize`仅TEST_ONLY SENT/ACK/RESULT/ACCEPTANCE，缺可信实际接件/worker start/独立review、双方实例和活跃权限proof；原系统受保护只读接口材料待实际对接。十分钟hook与私有仓用途未定，不加timer、不push、不新增权限/公开端口。
- 本次代码/配置/数据恢复边界分别记录：隔离代码可丢弃或以原144a另建候选，原业务未被修改；没有安装或配置变更，也无权推断现网配置可回滚；不操作业务数据。请main派非作者按本delta及真实父提交独立复审，不能由作者自审或用此报告关原目标。
