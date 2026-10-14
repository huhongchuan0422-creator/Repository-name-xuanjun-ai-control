# Work 原7项＋新增10项：基础接线与验收

来源：PR17登记6161577172；原登记6136253099、6136289637；
`plans/V27_OWNER_OPERATIONS_PRIORITY_20261010.md` 节点1.9–1.15和Issue19。
沿同一父任务；P2恢复与安装由dots接续。本分支不修改原安装制品或原7项源码。

## 原七项复用

| 序号 | 原任务 | 原开发PR | 本轮进展 |
|---|---|---|---|
|1|任务费用投影|54|复用已审源码；验证原dashboard缺成本生产证据时仍HOLD|
|2|Canary证据覆盖|54|复用已审源码；增加认证回执适配与fixture拒绝测试|
|3|依赖证据|55|复用已审源码；接实际tasks依赖图，不将DONE提升ACCEPTED|
|4|恢复前置|55|复用已审源码；绑定当前task/spec/checkpoint/fence及完整收件版本|
|5|人工告警|55|复用已审源码；只生成最小载荷，发送与收件人核验仍由现有outbox负责|
|6|运行用量|55|复用已审源码；缺生产证据保持null，不编造额度归属|
|7|交接证据|55|复用已审源码；证明展示不授予lease、ACK、停止或写入权|

## 新增十项交付映射

|序号|新增工作包|实现与检验|
|---|---|---|
|8|canonical任务费用消费者接线|`foundation_snapshot.costs`；认证/错任务/未知金额|
|9|canonical运行用量消费者接线|`foundation_snapshot.usage`；认证累计样本/缺失非零|
|10|canonical依赖图消费者接线|`canonical_page`＋`dependency_view`；DONE/缺依赖/环/截断|
|11|同任务同版本恢复适配|`bound_receipt`＋`resume_view`；所有绑定维度/旧writer未停|
|12|人工告警与现有outbox接口|`alert_payload`；固定调用方origin/缺上下文/无发送|
|13|同任务交接证据接口|`handoff_view`；完整停止/失效/副作用/继任ACK证明；无写权|
|14|同制品Canary收件接口|`evaluate_coverage`；精确来源/制品，fixture不冒充runtime|
|15|中文Owner基础摘要|`chinese_summary`；固定标签、状态与无权限输出，原始秘密不显示|
|16|同一只读事务与版本变化保护|query_only＋BEGIN、唯一任务主键、canonical spec/checkpoint/fence核对；WAL并发/重开|
|17|有界keyset完整性扫描|固定SQL、最多1000条、显式未完成和下次cursor；251任务/重开分页|

这些是可复用接线与隔离测试工作包，源代码交付不等于17项运行验收完成。
原7项既有通过检查不重跑；新测试只检验新增接口和原生产者的接线行为。

## 信任与调用合同

入口仅供受信任controller调用。调用方持有**现有**canonical只读连接，设置query_only并开始读取事务；本模块不打开生产DB，不建表或第二队列。
绑定对象精确包含task_id/spec/checkpoint/source commit/artifact/fence/epoch。
模块从现有tasks及execution_specs核对task、spec、原始checkpoint字节摘要和fence；
release/artifact/epoch真实性与有效执行权由现有controller核验，不能由本模块证明。
同事务一致快照不等于最新写权限：WAL外部写入可在本次快照之后发生，任何操作前仍须canonical原子重核。

外部证据envelope包含payload和signature。payload固定kind、binding、observed_at、data，
签名覆盖完整规范JSON字节；调用方注入现有认证验证器，不能把上传包提供的函数、keyring或`verified=true`当作验证器。
300秒时效、未来时间拒绝、严格整数fence/epoch、256KiB限额与每种原模块数据校验生效。
上游解析也必须执行输入字节、对象深度和大小上限；此Python函数不提供外部HTTP入口或任意JSON认证服务。
验证器异常可让整体读取失败，禁止失败时返回“通过”。

当前冻结102 package的dashboard有费用/用量/依赖调用，但无真实成本用量生产者、无canonical依赖独立验收digest。
本轮不伪造producer：缺失时原模块维持HOLD/null，DONE仍非ACCEPTED。
认证费用/用量回执只展示可信调用方提供的指定任务证据，不证明其component/run清单完整，亦不估算收费或剩余额度。
依赖图只读现有tasks，不用外部自报PASS覆盖canonical；遇未完成扫描则HOLD。
原人类告警函数要求可用于安全路径的task ID；不兼容ID明确HOLD，不擅自改ID。
中文摘要仅表示视图状态；所有流程仍无execution/resume/release/send权限。

## 复现

`pins.json`固定PR54/55逐文件SHA256。`bootstrap.py`下载7个已审模块和
原artifact11865804223，验证归档SHA256后只读取3个固定原生产者文件：
execution_ledger、owner_dashboard、activation_control；不任意解包、更不安装。
token仅bootstrap步骤可见；跨host重定向去Authorization；超量、摘要变化拒绝。

```bash
python3 -B evidence/work-17-integration-20261014/bootstrap.py /tmp/work17-new-private-fixtures
XJ_FOUNDATION_FIXTURES=/tmp/work17-new-private-fixtures \
  python3 -B evidence/work-17-integration-20261014/test_foundation_integration.py -v
```

测试在临时SQLite WAL中调用原ExecutionLedger.register_spec和原Owner dashboard。
测试签名钥匙、UK_RUNTIME标签和凭证均为fixture，不代表Owner授权、独立审查或英国实际运行。
39项新增测试本地Python3.12通过；3.6语法解析通过，真实3.6运行未测。
GitHub Hosted精确版本CI待回执；UK部署、现有可信validator接线、真实成本/用量producer、
独立验收映射、outbox发送/ACK、17项最终验收仍待相应门禁。

独立审查者须审核本次新增模块、bootstrap及工作流；本开发会话不自批。
部署前按真实controller合同核对target tenant/owner、keyring、完整inventory和activation变更，
与dots当前P2事务分别隔离；禁止将本源码CI结果用于P2恢复放行。

## 独立审核后续接（2026-10-14）

原head14619fde的39项隔离检查已获另一ChatGPT会话的限定范围源码审核，
PR72回执6161833019，PR17同步6161834490；不授予部署或运行权限。
本次按审核建议新增`producer_inventory.py`和21项检查，原七模块及
`foundation_integration.py`保持不变。`complete_producer_view`分别认证现有controller
清单和生产者记录，两者绑定同task/spec/checkpoint/commit/artifact/fence/epoch，
清单digest及整数revision必须相同；完整标志必须为布尔True，component/currency/kind
或run/provider集合精确相等。缺一项、多一项、换币种/提供方、过期签名、冲突重复均HOLD；
清单匹配仍不把未知值当0，也不授予quota或执行权。

真实canonical inventory producer尚未存在于本分支。本模块不生成清单、添加表、
签发批准或接受提交者自带的validator。两个验证器须由受信任运行时配置，并核对各自签发者
角色、来源、任务范围及revision；仅签名正确不证明清单完整。调用方必须直接取得当前
完整清单，不得把收到的局部records反推为expected清单。本辅助函数仅显示已认证声明的匹配，
不能证明源系统没有漏记。实际controller接线和实机审核仍待完成。

本地只运行新增21项，原39项通过证据保留。CI加入21项新检查；新提交须独立增量审核，
旧head的通过结论不扩展到新文件。原清单完整性提示继续保留。
