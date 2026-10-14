# P2 epoch3完整恢复候选：单次完整独立审核材料

状态：英国首轮160项、最终增量34项及完整预检证据已齐；请求一次完整独立审核。此文档本身不是批准。
代码负责人：Dots；独立审核：ChatGPT第5项；实际执行：Owner人工。
沿用PR17、PR58原请求6159620928及原canonical ledger。

## 精确候选

- HEAD：3f373b9766065149b9f2f402246fbb826a0f0bb3
- Tree：81520bac146ed72a4fb3103681945833a825f69a
- 分支：repair/p2-chatgpt-clean-review-20261013
- 包：evidence/p2-install-preparation-20261013/epoch3-recovery-kit.tar.gz
- 包大小：253222字节；Git blob：5a5930c52510225bc9b624730c9e202e4d70ae5f
- 包SHA256：a9c6bb2fa9bfc0114256216a6c15fe2dde241b28174e633f118e5000052524d8
- Kit manifest：89eb2624d3aaee99117e6292f547852a61cce88d119cbb0fab57e0539c8aed5b
- 入口SHA256：0152ae2b5f2bef0063175b25d1db0991845d6b9d17ba364f0dbb05280cde3fef
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

- 本地Python3.6.8最终聚合：168/168 PASS；epoch3-final-aggregate-local.results。
- 首轮实际打包test-only入口：160/160 PASS；最终打包affected-only入口：34/34 PASS，root映射临时目录，固定主机名/kit路径仅在本地测试中替换。
- 实际102文件installer staging与6项 --help smoke：PASS，临时本地release，无英国修改。
- 两次构建archive逐字节一致。
- 41份文本GitHub读回一致；包Git blob SHA1与本地一致并核对commit tree。连接器无法解码二进制作raw读回，英国下载命令强制SHA256。
- 单独入口/approve/parser/文件/ActivationStore/journal/失败路径等测试已包含。
- 真实ActivationStore及持久化回执用临时文件；服务器服务/TLS/CLI/GitHub接口在driver测试中模拟，不能当生产E2E。
- 本地Python3.6.8的ctypes重编译与sinpi工具链补丁只影响本地，不能称与英国Python字节一致。
- GitHub Hosted CI：本候选尚无绑定成功回执，不填PASS。
- 英国首轮test-only：160/160 PASS（Owner原始回执；first kit）。最终affected-only：34/34 PASS（Owner原始回执；final kit）。不是相加宣称194个独立测试。
- 最终英国verify-only：PASS；snapshot SHA256 e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e，与首轮一致；epoch=3、install_admission=NOT_GRANTED、production_resume=NOT_EXECUTED。
- 首轮原始回执SHA256 e0864a402a7a62dcfd76812456b0aacc59ffd7e60c4c1ce9b4b9b66a8c49d25c；最终原始回执SHA256 6bc4c9d920958e0332cb814b79a1708c577bca21c34c77bf732fd9175b53bb46。
- 生产恢复：NOT_EXECUTED；生产验收：PENDING。

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
  "recovery_kit_manifest_sha256": "89eb2624d3aaee99117e6292f547852a61cce88d119cbb0fab57e0539c8aed5b",
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
  --kit-manifest-sha256 89eb2624d3aaee99117e6292f547852a61cce88d119cbb0fab57e0539c8aed5b
  --operation resume
  --review-id <独立审核人真实新批准ID>
  --review-body-sha256 <真实批准正文SHA256>
  --snapshot-sha256 e297a8db0b4f2e2641ee3aeb6c94119a7ec5034a50a44a0e93723c996205df4e
```

失败隔离由同一入口自动执行一次，不另发可重复rollback命令；要求完整撤销全部安装副作用的审核人应明确HOLD，本候选没有把保留现场策略冒充全量回滚。执行期间不要重复点击/启动，不用外层短timeout强杀安装；断线先读原attempt状态，不猜测或重试。
