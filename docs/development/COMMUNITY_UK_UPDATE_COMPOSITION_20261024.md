# 原 UK preview 更新 composition 与精准审批候选（未执行）

本轮新增 `scripts/community_preview_update_composition.py`，不改已审 a932
controller/planner/原 transport/原只读核查器，不重建 f131。不存在已接好的
root composition 可复用：a932 的真实 readers 是必填依赖，此前尚未组合。
本文件是供根独审及 Owner 后续精准确认的源码方案，不是现场授权或操作回执。

## 三个版本分别冻结

| 对象 | 准确绑定 |
| --- | --- |
| 产品源码 / Tree | f13155ed63a3137d41766ee587d9b4b96a81477f / c31a9b1df006eeacd78ae3f9921073f3fe77d2c3 |
| 已审 controller / Tree | a9324156f94040bb6ff0243815bb91abe2f67b2a / b0e76fe43a5d31c3c0fa33d64e7d8d7c558d297b |
| 本轮 composition | 后继提交的文件 SHA256；审批必须绑定其实际 bytes，不把它当产品 source |
| release image ID | sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a |
| image Run / Job | 40059478387 / 120769700068 SUCCESS |
| artifact | 12546452389；outer57016858B / c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e |
| inner tar.gz | 57365044B / eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875 |
| artifact 到期 | 2026-10-27T03:44:30Z；准入前检查，不下载或加载镜像 |
| 产品 receipt | deploy/community-preview/f131-image-receipt.json；原样复用，含 source artifact、OCR90aca、stamp0444/User10001:1008/11层独验事实 |

03:00 根的真实观察证明原旧容器/image 可观察且前后相符，OCI准确为
2330dd55c07f58d7f45a7c4510a97610dd4735d6。它不是 f131，且此交接没有当前完整
containerID/imageID 原值。不能用旧历史818fe0/0846…补当前值。现网 health200/READY
仅PROCESS_AND_DATABASE_CONNECTIVITY，runtimeSHA/version_source/freshness仍UNKNOWN。
本轮不重新连接、查看服务器或运行原2330固定升级器。

## 已实现的真实来源组合

入口是 host-only `observe_current(backup_fd=...)`、`compose(approval_sha256=...,
backup_fd=...,execution_enabled=False)` 及返回对象的 `update.run()` / `update.recover()`。
没有 CLI、HTTP/listener、dispatch、远程执行器、环境参数或请求 body 权限入口。
默认禁用在任何读取/建 journal/transport 前拒绝；没有 shipped caller 自动打开。
未来只能由原已认证 root 执行路径在独审、Owner具体批准之后调用；布尔值本身不是授权。

`observe_current` 仅是待批准的只读函数，不在本轮运行：固定 NAME
xuanjun-community-preview解析ID/image → 固定ID的两次真实完整投影 → 再查固定NAME
不变。来源是原Docker socket的只读模板，不接受调用者填的哈希充观测。继承原
validate 的nonroot/mounts/资源/隔离要求，另查PortBindings/PublishedPorts/devices/capadd
为空；不读取Env、Labels全集、私有配置/DB正文。

`read_current` 与 `LiveBindings` 以原有界 readonly capture 执行固定Docker inspect
（8s/32768B；image8s/4096B）。原 parent_fd/safe_file 进行逐父链no-follow、owner、mode、
类型、前后identity复核。实际计算以下五个固定摘要：

- config：原config目录及host.json/center-keys.json/wechat.json的元数据，不读正文；
  文件身份含device/inode/uid/gid/mode/nlink/size/mtime/ctime，单链接。
- data：原data目录和原runtime目录的device/inode/uid/gid/mode。
  目录size/mtime/ctime会随合法对象/socket写入改变，不冒充稳定身份；不读DB/遍历数据。
- routing：仅原community-preview.inc及共享xuanjun-p2-owner.conf两文件sha256；
  后者仅路由文件摘要，不读P2运行或数据，不修改Nginx/证书/端口。
- isolation：原完整窄Docker投影，排除仅状态变化的running/status和已独立绑定ID/image。
- backup_reference：既有root0600单链接regular引用文件的受保护路径+元数据摘要。
  descriptor必须由原root调用方预先按批准来源打开，范围仅原/opt/xuanjun-community-preview/
  下的既有文件；路径/引用本轮UNKNOWN，不编造，不创建，不读其正文。

备份引用摘要只证明“同一个受保护引用”，**不证明备份内容可恢复/数据库可降级**。
Owner/root需独立核实实际备份/恢复及数据版本兼容证据，再把backup_verified_at和兼容审结
写入受保护审批。旧receipt或旧rollback容器不能充当数据备份。本轮测试中的existing-reviewed-
reference.json只是私有临时夹具名字，绝不是现场既有路径。

真实 live reader 每次重新读上述来源，跟踪冻结旧ID跨rename，不在执行时拿NAME的新容器
替换旧身份。每次前后重验审批/源文件固定摘要、600秒审批/备份/原观测有效期和root/hostname；
变化即HOLD。代码对重复读间的变化拒绝，不宣称文件系统/Docker跨资源原子快照。

`actual_health` 复用已审固定URL HTTPS probe（TLS、禁proxy/redirect、JSON、4096B），
并通过原Unix socket /run/xuanjun-community-preview/preview.sock读取/community/health。
两者在限时隔离Python子进程（10s/10000B）中完成，逐一检查远端integer observed_at
600秒/+30秒、结构及私有/公网版本/状态一致。直接保留公网响应的远端timestamp。
**不调用 observation.health() 的本地采集时间投影充远端时间，不回填缺失runtimeSHA**。
新版本最终仍由原controller exact_health要求f131+IMAGE_BUILD_STAMP；旧rollback不要求新SHA，
但若旧health没有远端时间，恢复后的验收会HOLD而非虚报ROLLED_BACK。任何health读取不明均
不构成自动恢复许可。

## root 审批与固定 journal 组合

固定 proposed 审批文件 /opt/xuanjun-community-preview/update-approval.json；本轮不创建。
root0600/单链接/no-follow/父链受保护/65536B及外部审结的准确文件SHA必须同时成立。
固定字段见同目录结构清单；拒绝多字段、bool时间/version、错误源、过期、空备份/未审兼容。
审批冻结**人工所见的实际current tuple**，不在执行时用latest替换。

composition自身及a932 controller、原planner/upgrade/observation源文件都必须是受保护root文件且
SHA准确（固定pin在源码）。原f131 receipt也固定digest；测试不能当安装证明。
原身份/权限/root路径不变；没有创建账户、grant、secret、服务或修改Docker socket权限。
根仍须审未来原root调用载体及其源码安装目录/所有者；当前现场安装位置/bytes UNKNOWN，
不能把本工作区root测试权限当服务器安装完成。

compose先验证真实current、已加载release image准确ID/OCI/User、无恢复名字冲突，再打开
controller的固定journal父目录 /opt/xuanjun-community-preview/update-journal。父链no-follow/
root0700/固定fd；**不创建父目录**。父目录不存在则拒绝，不走/tmp或其他路径替代。
只有未来精准授权并调用compose才会写lock/active/attempt/events/checkpoint；本轮零现场写入。

## Owner 可具体确认的动作边界（当前未请求执行）

必须先把以下UNKNOWN补成根独审通过的准确值，再供Owner确认同一固定attempt：

1. 原host iZd7oeikknn1z21sq6ji6zZ / 固定NAME对应的新鲜containerID、imageID、完整current
   五摘要及observed_at；仍必须是上述已观察OCI、运行中nonroot10001:1008/原隔离，无新增端口。
2. 原config/data/runtime目录及文件身份、两份路由摘要、旧rollback名字无变；确切既有备份引用
   descriptor/path/identity、备份验证时间和恢复/降级兼容结论。只补这些绑定，不重复连通调查。
3. 原root源码调用载体/安装路径及逐文件SHA，固定approval root0600与准确digest，固定journal
   parent的root0700/no-follow存在性；不存在只能另经Owner明确批准建立，不能本轮隐式准备。
4. 固定f131 release image已在原Docker中加载且ID/OCI/User匹配、预期新rollback/failed名字不冲突。
   镜像传输/校验/加载若未获批准，必须单列批准；composition不下载、不load、不pull。
5. 在600秒内冻结审批和current/备份观察；新runtime真实SHA/stamp/远端时间由运行后实际响应
   判定，当前UNKNOWN。不能预填PASS；实际执行记录必须保留原/新ID和准确image。

拟允许的单次更新影响：

| 范围 | 具体变化 / 保留 |
| --- | --- |
| 原root控制源码 | 仅审结composition+固定pin依赖+f131 receipt；安装位置待原root核定，不替换产品镜像源码 |
| 审批/journal | 准确审批文件；root0700父目录（若需建立须另批准）；本attempt的lock/active/events/checkpoint；不删历史 |
| 容器 | 停准确旧ID → 旧ID改唯一before-f131-ID名字 → 原run_argv启动固定release image；真实新ID落盘；不删旧/failed容器 |
| 配置/账户/数据 | 同一原config RO、data RW、runtime socket bind；不改账号/授权/密钥/私有文件，不自动备份/恢复或迁移数据 |
| 资源/路由 | UID10001:1008、0.5CPU/512MiB/64pids、readonly/no-new-privileges/capdropALL；无TCP publish，原Nginx/DNS/HTTPS不变、不reload |
| 恢复 | 仅controller明确KNOWN_FAILURE+已持久新ID；先新停/socket消失 → retain failed → restore/start旧ID；读后再次证新停 |
| UNKNOWN | 保留同attempt原证据，停止、不得重试/另开attempt/盲启旧；不保证外部root actor不能在最后观察后改变状态 |

这不是Docker原子事务，也不是数据库自动回滚。共享可写data若被新版本改变，旧容器存在并不证明
兼容；无独立备份/降级审结不得批准该更新。恢复后stamp/远端时间缺项仍HOLD，预览/生产不通过。

## 同版测试与后续预览

仅新增composition定向测试和原Hosted专项分支；原a932 46+根5边界、f131镜像及31d3业务/OCR/
66路由资产全部复用。测试真实临时受保护文件投影+journal+controller，Docker/host/health/审批来源
是明确合成隔离夹具，绝非现场回执。默认零调用、身份/配置/目录/路由/备份更换、symlink/hardlink、
新端口、审批过期/错scope、远端时间缺损/过期、私有公网差异均拒绝。

当前官方mini preview仍需原branch HEAD==input/runSHA==真实backendSHA。后继控制源码HEAD与
f131产品不相等，不能拿旧Run给新SHA准入，不回退分支、不弱化门禁。Owner后续批准同版产品/
预览候选前，默认preview_enabled=false；不dispatch、SDK/self-hosted、上传、部署或生产OCR启用。
生产ocr:use/store/真实引擎仍独立HOLD，不能用审批或fixture补权限。
