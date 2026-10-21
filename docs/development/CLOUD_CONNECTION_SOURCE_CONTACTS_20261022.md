# 长期接线：源码接点与实际准入断点

承接PR17 #6322049200；基线9351d1ef935defc569d579bdfe4ca238b203c808。
本窗口为开发Writer，不自签增量审核。线上仍原版本；本文件不授权上线。

## 源码调用链

PrivateMcp.read_project_chunk（内部方法，非注册工具）→worker.ExistingProjectFiles.read→private_transfer.export_chunk→bound_job（原connection_jobs）→固定根描述符读取→Receiver.accept/reconcile（原SQLite及私有接收根）。

所有新增入口默认关闭：main不传project_files，worker适配默认enabled=False；没有recipient_provider、批准catalog或受保护根引用即拒绝。项目文件必须由原SUCCESS/fetch_approved_object/InvokeId/项目/接收方/Manifest/预算/完整SHA证明绑定。probe及fetch_os_release不能授权其他文件，未知operation不得落成probe。原Queue的允许operation不扩展，未实现新的云端收集注册，也不伪造SUCCESS。

测试使用明确标注的临时未来SUCCESS记录和接收方fixture；不是云调用或接收方认证验收。实际MCP仍只注册两个旧只读工具。内部方法供候选集成测试，不是可用的线上传输入口。

Loop.tick→credential_lifecycle.record_on_existing_queue→原connection_outbox→Loop.flush。host-only expiry_watch默认None，main配置字段不扩展、线上hook未启用。相同代际/阈值去重，UNKNOWN不重投；停止阈值先写原通知，再HOLD，不领取/执行任务。不创建或轮换凭据。

runtime.code_pin纳入queue/worker/runtime/private_transfer/credential_lifecycle五份可执行依赖。新pin不能当旧线上pin。旧enroll.py继续绑定原SOURCE_COMMIT/三模块，不改旧安装清单；原enrollment测试使用原两份冻结源码fixture，仍逐份核原硬编码SHA，queue/unit未变直接复用。候选上线必须另行提供新完整闭包，不能运行旧enroll安装本候选。

## 接收方身份实际来源：缺失，保持拒绝

已核PrivateMcp.handle仅接stdin JSON；params、_meta、clientInfo均不可信。隧道的工作区关联只有通道访问限制，未传入可验证的逐调用接收方身份。原GitHub receive验证actor，但不能证明当前MCP收件人。当前main不注入recipient_provider，不从参数、环境变量或工作区名造身份。

最小可评审绑定方案：由既有受信传输网关验证平台签发的调用主体，验证issuer、audience、有效期、签名及会话绑定；在工具JSON之外向适配器提供不可由请求覆盖的主体；root维护主体到recipient_id及项目catalog的精确映射，撤销/过期立即拒绝。需先取得平台支持的真实主体接口及其验证文档/样本，不能把拟议字段写成已存在接口。缺此来源，通用私有文件上线仍HOLD。测试provider仅依赖注入契约，不是身份实现。

## 官网三组依赖与原接口

依据PR122/PR17窗口5 #6321560629，采集器SHA c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f。

|组|准确内容|原接口接点|当前状态|
|---|---|---|---|
|固定20项|CURRENT、RUNTIME_CURRENT两链接；R2_RECEIPT、INSTALLED_PUBLISHER、RUNTIME_UNIT、NGINX_01–13共16文件；STATIC_LOCK、CANDIDATE_LEDGER两元数据|action_binding.prepare绑定website_baseline_collect/准确adapter与plan；原Queue/worker需经原准入登记该固定动作，回原InvokeId，结果按catalog交付|原Queue尚未注册，未采集；不能拿OS结果替代|
|inputs/source|同现场准确根、受保护归属、版本/摘要与可读引用|原动作输入Manifest/plan绑定；传输catalog的root_ref由host登记为准确根，仅按固定对象读取|UNKNOWN_NOT_READ；没有根引用不猜值、不扫描|
|范围外运行状态|service active、实际加载Nginx/runtime sandbox、Writer/Fence及未决事务、输入有效性|原项目运行状态/事务接口的单独可信回执，按action_binding原门禁接入；不得由20项文件推断|UNKNOWN；没有接口/回执，不造PASS|

20项逐路径由原采集器冻结维护，不复制另一份扫描器。现有8历史staging范围不扩充为20项许可；不获取锁、不读取客户DB正文/私钥/token。

B5仍沿原完整选择：#6316275680禁止拆成三小批。#6316024096三份元信息Manifest cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba的selected_members为空，不能代替完整批准catalog。原更小16MiB项目预算保持；不能用通用256MiB上限提升B5预算。不收集未批准对象。

## 集中剩余项与验收

1. 平台真实受信接收方接口及root映射，当前缺失。验收：真实主体正向、错主体/过期/撤销拒绝，工具参数/_meta不能替换主体。
2. B5完整批准catalog、根及完整选择；官网20项动作准入、inputs/source准确引用、范围外运行/事务回执。验收：原任务/InvokeId与完整对象SHA、接收范围和原预算一致；缺件集中HOLD。
3. 新候选独审及精确线上改动确认：新执行闭包pin、私有MCP独立SHA、固定host配置、项目/接收方范围、唯一服务Writer和回退。当前不改服务、不注册工具、不新增权限。
4. 准入后实际项目文件双端SHA、重启恢复及固定项目动作验收。不能以本地fixture、Hosted或OS文件成功替代。
5. 现有平台凭据2026-11-20到期，具体时刻UNKNOWN；候选保守停止界2026-11-19T00:00Z。正常续期需原平台获准流程、单次集中准确变更确认、私有保管、旧代际保留审计；不重试已拒绝永久期限，不在本轮创建/轮换。
6. 封存conn-second-window-uk-20261021T162627Z；原工具仅返回安全检查屏蔽，未给具体Reason。不得改编号/账户/路径重投，不能据此宣称所有合法源码工作禁止。

SOURCE为候选接点已实现；LIVE新增能力NOT_EXECUTED。只有原三机/常驻/续期/旧只读收件及重启证据可复用。未声称长期接线全部完成。
