# P2 epoch3完整恢复候选：单次完整独立审核材料

状态：英国首轮160项、前次增量34项证据保留；B1修复新39项及最新完整预检已通过（依据Owner实机原始回执）；请求一次完整独立审核。此文档本身不是批准。
代码负责人：Dots；独立审核：ChatGPT第5项；实际执行：Owner人工。
沿用PR17、PR58原请求6159620928及原canonical ledger。

## 精确候选

- HEAD：07e81116edb0dcf851259f6a292a8a25e735cca7
- Tree：552839cc0f55660ffe3d982c571e2c37b83763cd
- 分支：repair/p2-chatgpt-clean-review-20261013
- 包：evidence/p2-install-preparation-20261013/epoch3-recovery-kit.tar.gz
- 包大小：254327字节；Git blob：6fa72f11e933faccdc02ea4de9e8c6a5021fff9a
- 包SHA256：7e3228b293d0737d27a3f3fca57385f5b6c5628cfddf6488ce1c17c1017d619f
- Kit manifest：1e13f9e1b6c2fddc135c314fbfb4c6f2b687466ef01208321116a9de10a3c71c
- 入口SHA256：5c494fe7b5c8737a972d6e012e76a74d17b005a978462a6b3ab9b3cb8daa2848
- Runtime manifest：338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09
- 私有计划SHA256：0966ab156508228670faaadbba97ff62e19dac8451cced3598eda4eb0bea7f76
- 运行源码修复来源：1a35f744224a64d73128196f6212195d15a9d0a7 / fa23b50843e4fc579348f403322dc3224c8ff78e
- 原制品11865804223的100个未变runtime文件沿用历史证据；另2个runtime修复、19个helper及新入口须审查。

任何源码、包、manifest、私有计划、入口字节变化不得继承本次未来批准。

## 当前现场及历史准入

最近Owner回执：HOLD，activation PREPARED epoch3；TLS先失败，随后drop-in缺失导致旧恢复再次失败。
批准6160188919及6161965867均已消耗；旧resume禁止重跑。
旧数据库、generation、backup、六项旧隔离和历史通知状态继续沿用，现场变化必须重新核实。
历史Telegram通知UNKNOWN_NO_REPLAY；不得启动旧writer。

现场证据已确认：24目标维持原状态，7个bootstrap对象匹配，16个RPM版本匹配，2个publisher完整内容与身份匹配；TLS三个目录空；普通私有空Certbot配置解析成功。
上述证据不是本候选的实时准入，新verify-only快照必须再次通过。

## 单一事务完整调用链

1. 外部Owner命令校验下载包SHA、入口SHA、Kit manifest。
2. 入口以 -I -B 启动，校验固定主机/root、受保护目录、所有helper及102个runtime文件，拒绝额外模块/字节码。
3. 由原私有计划和两个精确runtime修复重新生成计划；批准绑定新计划、kit、runtime、snapshot。
4. PR58实时读取真实评论，验证指定GitHub作者、目的PR、完整机器可读正文、body SHA；旧批准ID/marker拒绝。
5. 独占现有install lock，完整只读现场预检，第二次读取批准，比较精确快照。
6. 原事务目录O_EXCL创建epoch3-recovery-execution.json并fsync；每阶段先INTENT后COMPLETE。
7. 使用原精确installer暂存新release；保留六份旧回执、旧TLS树及旧TLS日志。
8. 原ActivationStore同一journal执行PREPARED3→PREPARED4；canonical DB身份保持不变。
9. 对原native binding做精确CAS并私有备份，保留原0644权限；写独立TLS候选引用。
10. QUIESCED4；保留现有RPM/NSS/bootstrap/publisher，执行新TLS、24目标和原插件安装调用。
11. 以原数据库access流程重新打开既有generation；ACTIVE4；仅恢复Gateway文件并启动精确新服务。
12. 复用已审原postchecker，传入新activation身份，核验NSS、服务、真实证书/续期测试、HTTPS鉴权。
13. 最终仅COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE；生产验收仍须第5项复核。

## 失败与回滚边界（必须明确审查）

本候选采用FENCE_STOP_RETAIN_NO_REPLAY：先撤销activation，再逐一尝试停止精确新服务，独立核对所有PID/cgroup为空，恢复原boot enable状态、重新屏蔽两项旧Owner服务、恢复Stage1/Gateway屏蔽，并再次测量旧隔离。三组恢复分别尝试，任何一组异常不跳过其余组，最终仍须全部证明；证据保留。
某一stop失败不跳过其余stop；任何不能核实的结果UNKNOWN，进入HOLD。
不调用旧generic restore，不删除NSS/RPM/bootstrap/publisher，不自动恢复旧服务。
这是一条保留现场的失败隔离/受控恢复策略，不宣称完整撤销全部安装副作用。
不提供脱离事务的一键回退旧环境命令；失败后读取新旧回执并由独立审核确认下一次有限恢复。
不无限重试，不因超时猜成功，不清理未知残留，不重发历史通知。

## 测试证据及限制

- 源码负责人本地Python3.6.8最终聚合177/177 PASS；epoch3-b1-aggregate-local.results。
- 实际最终包的affected-only入口39/39 PASS（本地root映射临时目录）；epoch3-b1-packaged-local.results。
- 英国首轮160/160 PASS，前次修订34/34 PASS均保留。本次B1修订39/39 PASS，含9项新增边界测试。各批次重叠，不得直接相加为独立测试数。
- 本次英国原始回执epoch3-uk-b1-owner-receipt.txt SHA256：3efeca693481d0b1d79d5490b9a17cc4b9d64a7d1d7a9135b3daf3b8a9313484。
- 最新完整verify-only PASS：epoch3、install_admission NOT_GRANTED、production_resume NOT_EXECUTED；snapshot e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e。连续三批快照一致。
- 实际102文件installer staging与6项help-smoke、24目标source/rendered hashes、3插件引用、dispatcher/TLS身份：本地PASS，未冒充英国正式安装。
- 两次最终构建archive逐字节一致；新增源码文本GitHub读回一致；binary Git blob SHA1匹配，Owner英国实际下载SHA256通过；ASCII transport读取后与本地archive编码一致。
- Driver服务/TLS/GitHub调用在测试中模拟；ActivationStore和attempt journal使用真实临时文件。不能把这些测试当成生产E2E。
- 本地Python3.6.8有ctypes/sinpi工具链修正，仅本地，不能说与英国Python字节相同。英国回执单列。
- GitHub Hosted CI：没有本次绑定成功回执，不填PASS。
- 生产恢复NOT_EXECUTED；真实ACME/HTTPS/通知ACK/完整P2-P3 E2E和生产验收仍PENDING。

## 独立决定要求

英国回执已补齐，请对全部材料一次性复审：要么给出精确批准，要么一次列出所有剩余阻塞。不接管源码、不另建审核任务、不重复不受影响的历史验收。
批准如成立，必须使用epoch3_approval.py的MARKER与expected()精确JSON，绑定该kit和实际最新snapshot。当前没有批准正文可用于resume。

## Owner操作

当前仅发送了测试与只读预检命令附件，其作用是下载绑定包、准备独立候选目录、test-only、verify-only。不存在resume参数。
正式恢复命令须待新独立批准后填入真实review-id、body SHA、snapshot SHA；仍使用相同已审核入口和kit SHA，不现场改脚本。
新受保护回执：原事务目录/epoch3-recovery-execution.json。
旧install-receipt.json保留历史HOLD，不用其值冒充新执行结果。


## 安装前细节核查覆盖及边界

- 权限/目录：固定英国主机root、原事务0700、install lock0600、activation lock0644、native binding0644；禁止符号链接、未知目录内容、字节码和宽松写权限。
- 版本链：archive→kit→19 helper/入口/tests→102 runtime→实际renderer→24目标；真实本地installer暂存24/24 source/target绑定、3/3插件引用通过，dispatcher/TLS配置绑定通过。
- 原资源：16 RPM、NSS身份、7 bootstrap、2 publisher目录内容和身份保留；不重放创建，不泛化删除。
- 数据：source/backup/generation及WAL/SHM/journal集合、实际复制后manifest、FD持有人、前后字节/身份、原ActivationStore journal/canonical identity。
- Writer/调度：旧Stage1/Gateway/Owner服务及通知timer隔离；Runner inactive/ConditionResult=no；进程/cgroup/定时任务扫描；读取错误失败即HOLD。
- 启动：仅在精确PREPARED4→QUIESCED4→ACTIVE4后启新服务；原Gateway文件恢复前完成Fence/DB重开；原Stage1不启动。
- TLS：保留旧空目录/日志；常规client.ini修复；真实ACME签发和续期dryrun属于正式执行，当前不冒充已通过。
- 失败：每个阶段先写INTENT；任意阶段失败都先Fence、逐项stop、核实停止，再恢复启动状态和旧屏蔽；任何不明结果HOLD且禁止重试。
- 外部依赖：GitHub API、DNS/ACME网络、实际服务启动只能在执行时重新验证；本地及只读通过不能保证这些未来外部动作成功。
- 验收：postchecker涵盖NSS/服务/HTTPS鉴权/证书续期；真实通知ACK、完整P2/P3业务E2E和最终生产验收仍单列PENDING，安装成功不等于项目验收。
- 上述结果是源码负责人自检及Owner实机回执，仍须独立审核人审阅，不宣称完成独立审查。

## 审核人机器回执格式

若且仅若独立审核通过，在PR58新建一条正文仅包含下面marker和JSON的批准评论（不能加代码围栏或额外解释）。这份材料中的示例不是批准，也不能用本送审评论ID启动恢复。详细审核结论可另写，但对同一完整候选作一次决定。

```text
CHATGPT_NATIVE_TASK5_EXACT_EPOCH3_RECOVERY_ACCEPTANCE
{
  "authorized_attempts": 1,
  "decision": "APPROVED_ONE_EXACT_EPOCH3_RESUME_WITH_FENCED_RETAIN_ON_FAILURE",
  "expected_epoch": 3,
  "failure_policy": "FENCE_STOP_RETAIN_NO_REPLAY",
  "historical_notification_replay": false,
  "legacy_restart": false,
  "production_acceptance": "PENDING",
  "proposed_prepared_epoch": 4,
  "recovery_kit_manifest_sha256": "1e13f9e1b6c2fddc135c314fbfb4c6f2b687466ef01208321116a9de10a3c71c",
  "recovery_plan_sha256": "0966ab156508228670faaadbba97ff62e19dac8451cced3598eda4eb0bea7f76",
  "reviewer": "CHATGPT_NATIVE_TASK5",
  "runtime_manifest_sha256": "338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09",
  "schema": 1,
  "snapshot_sha256": "e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e",
  "transaction_id": "c529c379-9341-4510-8384-fc6be1e412e5"
}
```


## 审核范围内的正式执行入口模板（当前禁止执行）

最终Owner命令仅填入审核人真实新评论ID及该评论body UTF-8 SHA256；必须先验证当前入口SHA256与kit manifest。入口自身再次校验完整kit、两次GitHub批准、实时snapshot及单次attempt。禁止替换脚本、修改文件或使用旧审批。

```text
/usr/bin/python3 -I -B <固定KIT>/epoch3_recovery_entry.py
  --kit-manifest-sha256 1e13f9e1b6c2fddc135c314fbfb4c6f2b687466ef01208321116a9de10a3c71c
  --operation resume
  --review-id <独立审核人真实新批准ID>
  --review-body-sha256 <真实批准正文SHA256>
  --snapshot-sha256 e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e
```

失败隔离由同一入口自动执行一次，不另发可重复rollback命令；要求完整撤销全部安装副作用的审核人应明确HOLD，本候选没有把保留现场策略冒充全量回滚。执行期间不要重复点击/启动，不用外层短timeout强杀安装；断线先读原attempt状态，不猜测或重试。


## PR58 #6165869434 的B1修复（完整复审必须包含）

首次停止状态验证异常导致后续恢复被跳过的问题已修复。
新版本分别尝试 stopped_before、boot、owner_masks、legacy_masks、stopped_after、legacy_after。
前面任何操作异常都继续后面的有限操作；初次验证异常即使后续验证通过也保持UNKNOWN/HOLD。
ContainmentIncomplete携带每项结果，由原单次attempt回执保存；不丢失部分恢复结果。
新增9项测试覆盖初始/最终/两次验证异常、三组恢复各自失败、事后legacy测量失败、组合异常及持久化UNKNOWN。
相关代码：epoch3_host_driver.py、epoch3_recovery_sequence.py；入口仅调整affected-only测试集合。

前次独立审核未完成整个archive、19helper及102runtime逐项核验。
请此次完成全候选独立审查：不能仅审B1 diff后宣称全部通过。
本次实测GitHub连接器读取binary及Git blob API均返回UTF-8限制，不能宣称独立下载验证已通过。提供同字节包的ASCII编码 epoch3-recovery-kit.base64.txt：可用GitHub文本连接器直接读取，base64解码后必须核对archive SHA256，再检查tar成员和所有manifest。该文件只是可读传输形式，解码内容与原二进制包逐字节相同，不改变执行制品。
包Git blob标识：6fa72f11e933faccdc02ea4de9e8c6a5021fff9a。
EPOCH3_REVIEW_INDEX.json列出包内所有helper、test、runtime哈希，供独立比较；该索引不是审核人验收证明。
