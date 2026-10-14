# 东京→韩国迁移：已授权主机盘点接线

沿用PR17及plans/MIGRATION_SEQUENCE_V1.md；不是新任务队列。Work17原PR72保持不动，P2归Dots。
Owner于2026-10-14明确：易币退出资源保障范围，小说暂保留，币安生产迁韩国，现有容量先承接，不预先扩容。

## 本变更实际行为
新工作流仅在本仓库Owner提交的指定迁移分支PR运行，在东京与韩国调用已由Owner安装的root-owned固定零参数盘点helper。没有checkout、不运行PR代码、不新增sudo权限。先核验主机、Runner用户、helper所有者和模式，记录实际安装文件SHA256；原控制仓库目前为公开仓库，只允许输出已授权的脱敏资源及服务状态，不能上传业务数据、配置正文或密钥。
migration-prep/inspect-helper.sh现已按Owner实际收到的安装命令逐字重建；本地SHA256=61bed97a32e970dd868f2d223c68ab41c012c484d314cb714c768629aac263c2，与两台首次Actions记录完全一致。新工作流在调用前强制pin该摘要，检查root-owned非软链父目录且group/other不可写；打印当前调用者sudo -l有效策略作为脱敏证据。没有更新任何主机helper或sudoers。

sudo -l列表不是所有sudoers来源、包含文件和env策略的完整审计；工作流明确FULL_SUDOERS_POLICY_AUDIT=NOT_VERIFIED。GitHub Connector不提供/actions/runners访问政策GET，浏览器未登录；GLOBAL_RUNNER_ACCESS_POLICY=NOT_VERIFIED。当前公开仓库Default Runner全局隔离尚未验证，保持生产操作HOLD。限定盘点成功不能被当作生产准入。
root盘点授权于2026-10-21T00:00:00Z失效。

## 已有证据与剩余工作
- 东京Owner控制台2026-10-14T09:17:59Z：固定helper调用通过；国内模型与韩国小说模型隧道active。
- 韩国Owner控制台2026-10-14T09:19:34Z：固定helper调用通过；小说active；易币API/调度active；可用内存1311988kB/磁盘26G。
- 这些是Owner提供的现场回执；本PR取得真正Actions调用及hash后另记，不能预填PASS。
- 备份导出、数据库一致性恢复、易币可回退停用、隔离安装、行情/持仓/订单对账、影子验证、重启及回滚、唯一订单writer切换均未执行；不能通过本盘点放行。
- 需完整资产清单与受保护配置/数据库位置，方能冻结备份与部署操作包，不能猜路径或把活跃SQLite直接复制作为一致性备份。
- 英国只读重跑job115771246865仍排队；不会等待它阻塞东京/韩国独立盘点。不能伪造旧Work STOP或canonical writer接手。

## 本地验证
bash -n通过；helper额外参数拒绝(exit2)通过。非目标主机拒绝另验。
原cdd07e1491d0f0e5cfd7706f6b494df142df04aa获独立限定通过(review5515796568/comment6165218990)，两机实调用38542109818通过。新增hash/父路径增量仍需新HEAD CI和独立复审。本PR不合并/不执行生产变更。
