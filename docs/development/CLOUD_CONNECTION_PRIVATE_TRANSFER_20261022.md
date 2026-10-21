# 长期接线：批准对象私有传输、原动作绑定及凭据到期候选

原任务PR17；需求/接单#6321126451；继承d1def9fb、#6321045032。
本文件是开发候选说明，不是安装许可、接收方身份签发或服务器执行回执。
不改已运行的queue/worker/runtime/private_mcp，不启第二Writer，不另建调度器。

## 已实现的源码与开发顺序

1. private_transfer.py：宿主已批准项目策略＋准确catalog SHA＋固定object ref；源端安全读取；接收端分块、完整SHA及原Queue数据库扩展审计；失败/重启可信对账。
2. credential_lifecycle.py：非秘密元数据到期判断、原Queue/outbox阈值预警和重启去重；不生成或更换凭据。
3. action_binding.py：固定项目动作的源码/制品/plan/原任务绑定；只给原适配器所需引用与下一状态，不执行命令、不消费Attempt、不签许可。
4. 对应三个新测试模块；原67项继承为回归，不将其重复累加。
5. 源码/Hosted/必要独审闭合后，再登记真实清单、可信接收方、私有根和原动作入口；实际项目收发/动作另有真实回执才记VERIFIED。

## 文件合同及权限边界

Catalog必须由宿主传入已批准SHA，不能以文件自身摘要冒充批准。宿主另传项目策略：准确project、接收方、root_ref、文件数、单件和总量上限。catalog不能扩大项目策略。
只接受已批准清单内的ref，文件相对路径属于私有清单，不是调用者自由参数；实际根由宿主预登记root_ref解析。authenticated_recipient只能来自经验证的原接收方上下文，不得来自工具参数、布尔标志或不可信_meta。

库的全局硬上限为64件、单件64MiB、清单总量256MiB、分块64KiB；项目原上限更小时取更小值。**不因此扩大B5原16MiB取件上限、原成员选择或官网采集器16MiB读取预算。**
接收方私有根总量512MiB/4096个条目停止；不自动清除失败文件腾额度。只检查本适配器保管根，不搜项目树或全盘。
源端逐级NOFOLLOW目录描述符、owner/mode、单链接普通文件、大小/完整SHA、变化/替换/时限检查；输出无本机绝对路径、原始配置或秘密。
接收端核manifest/project/ref/recipient/request/原InvokeId/大小/整体SHA及每块SHA，按序写入root私有.partial，完整校验后无覆盖发布.bin。

仅接受**原连接队列已SUCCESS**且operation=fetch_approved_object、原请求参数及原回执完整匹配的记录。旧OS任务不能授权项目文件；缺原记录不新造记录补空。
当前线上Queue仍只登记原probe/OS操作，MCP仍只提供原两项OS只读能力。本候选没有绕过该门禁，也没有把新operation直接塞进运行队列。

## 审计、异常与恢复

复用调用方原Queue.db，新增connection_file_delivery/events/failures表；没有新SQLite文件、AuthorityStore或安装调度器。
项目/清单/ref/接收方/原任务/InvokeId形成固定binding，防替换、UPSERT改绑及删除。失败审计仅保存固定错误码/摘要引用，不存正文、路径、凭据。
SQLite BEGIN IMMEDIATE；拒绝调用方已有事务且不提交或回滚它。双连接锁竞争、实际COMMIT BUSY、中断、短写及清理失败均保留现场。
写入成功但提交未知时不覆盖、不截断、不盲重传；完整对象可仅凭原绑定＋完整SHA可信对账，记录整件最终证明（events offset=-1），不伪称丢失的分块提交曾成功。
不完整且不能可信对账的多余字节继续HOLD。数据库仍被锁/损坏时审计可能无法提交，异常failure_audit_recorded=false；不得写0错误或PASS。
接收端重开只续原partial/原binding；已SUCCESS对象不重写。发布硬链接后中断仅在两个准确保管名同inode、总链接数2且完整SHA一致时完成原发布。

## 项目动作的准确准备范围

| 项目 | 已查原依据 | 本候选准备/尚缺 |
|---|---|---|
| B5取件 | #6316024096、#6316275680；原source manifest cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba；原INSTALLATION_CONVERGENCE.md | 不把三实现58922B或384边界当完整选择；原说明selected_members为空。由原B5 Writer冻结最终有界选择、父引用、大小/SHA及实际保管根后，才能登记catalog。不得启动SDK或直接提取旧批次。 |
| 官网固定采集 | #6320753243；ec4c3471ce05f658c1f4f6081c3eabc27b1b4979的tools/pr122_static_baseline_readonly.py，12809B，SHA c352c041ab62a1bf3c1c55afeea461ba935016e294975dfb515e19972365250f | 只准备该无参数、固定国内root入口的准确绑定；不编辑窗口5源码/workflow。其23项Hosted是否闭合及正常现场准入由原任务确认；inputs/source未知仍UNKNOWN。当前未调用它。 |
| 安装/更新/备份/恢复 | 原项目安装器及原Writer/Fence/事务/许可 | prepare只接受固定operation、准确源码/adapter/input/plan SHA与既有任务。READY仍ORIGINAL_ADAPTER_AND_GATE_REQUIRED；UNKNOWN只查原InvokeId或原事务；SUCCESS不得重放。没有新增Shell入口或假的安装实现。真实原适配器登记缺失时不得执行。 |

action_binding没有执行函数，不把host supplied registry字符串当已验证Writer/Fence。连接成功、准备成功或测试通过均不产生业务部署批准。

## 平台凭据到期及正常轮换方案

当前平台显示2026-11-20到期；没有精确UTC秒。候选保守停止界线为2026-11-19T00:00Z，**这不是推断出的平台实际到期时间**。
只接受已批准、非秘密元数据：credential_ref/generation/expiry_date/可选精确UTC/核验UTC/原来源ref。拒绝never、无来源、未知日期、未来/过旧核验及同generation改绑；不读取key正文。
按14/7/3/1天及到界停止阈值一次预警，使用原connection_outbox，由原Loop.flush负责发送和UNKNOWN不重发。新候选尚未挂入在线Loop，因此**预警还没有实际启用**；不另开定时调度器冒充接好。

正常轮换的集中变更单：

- 仅为既有隧道生成下一代Read/Use、其他权限None的有期限凭据；不重试被拒永久期限，不授予模型或Manage。
- 新密钥先保管到英国root0600版本化私有文件，元数据记录准确新generation/平台到期证据；值不进入聊天/源码/日志/截图/命令参数。
- 通过准确新profile、doctor、同一只读工具真实调用后，按获准方案原子切换引用；保留旧代及回执，旧代撤销必须在正常确认范围内。
- 验证失败不撤销旧代、不清理现场；旧代仍有效时按批准恢复入口处理，结果未知先对账。
- 上述创建/切换/撤销的实际对象、权限、接收方和回退方案须在行动时集中确认。本批未创建、更换或撤销凭据，未启用自动轮换。

## 原被拒任务及集中准入缺项

已回原聊天窗口只查询既有拒绝，不重试。其报告工具mcp__GitHub__add_comment_to_issue，原文“此工具调用被 OpenAI 的安全检查屏蔽。请仔细检查你发送的内容。”；原工具未给具体Reason。此处明确是原窗口摘录，不冒充本窗口新取得的底层审查报告。
conn-second-window-uk-20261021T162627Z保持封存；不改账户、入口、窗口或编号重投该操作。该限制不阻止本批独立源码开发。

上线前一次集中补齐：

1. 原项目真实批准catalog SHA、最终成员与项目更小预算、固定源/收件根及原成功任务/回执；当前没有把任何测试fixture作为真实清单。
2. 可验证的接收方身份接口或正常授权的精确私有传输接收方绑定；当前隧道工作区关联不等于逐调用recipient认证，禁止用参数/_meta冒充。新增持久访问须集中确认。
3. 新通用operation经原队列/worker的准确登记及受影响调用链审核；当前旧枚举保持拒绝，没有另建提交路径规避旧拒绝。
4. 原B5冻结选择、官网准确获准采集绑定、各业务原执行Writer/Fence/事务/恢复入口；不要求Owner搬材料，由原持有人在原任务提供准确引用。
5. 凭据非秘密元数据绑定与原Loop预警hook/新代码完整pin的准入；未接hook不得报到期预警在后台运行。

上述仅阻塞实际新项目收发/动作/预警上线，不阻止本批代码、回归、Hosted和原PR17交付。全部现场新动作NOT_EXECUTED；整体长期接线仍INCOMPLETE。
