# TC 现代保数据承接：TEST_ONLY -> 项目隔离 FORMAL（同 task，唯一正式入口）

适用：Owner 2026-11-27 17:42 批准（msg om_x100b7fa146d7fca4c06762aa1fcdd57，reply om_x100b7fa0a49ae0a4ce5483ff85c63a7），仅原低风险 task 首次项目隔离身份：小维托管首次项目密钥、小开开发、小审小验非作者核验。范围仅 tc-real-development-20261123-4d99c26f2b07 / spec 4d99c26f2b07beebb2863f141cfa0d959ef1e6144830d85da84e6451c77b2e7c / checkpoint b4fed6497d0cebe9042b3456c28feb4b45c59ffd61adcd62be49818a32129a00，READ_SOURCE/WRITE_SOURCE/RUN_TEST。不是其他项目授权、不是生产发布、不是全局权限；本文件与批准都不是"激活完成"。

## 与旧工具的关系（先读）
- 旧 `legacy_authority_migration.py` 只认 CANONICAL_LEGACY（application_id=0/user_version=0 固定指纹）。当前库是现代 supervisor schema（app=0x58534A31/user_version=3，profile=TEST_ONLY），旧迁移器不适用，不得对其运行，不得 SQL flip profile，不得新建空任务或伪历史授权。
- 本工具只做"离线、保数据、同 task id"承接；承接后正式 register/claim 仍走已装 F4 入口 `task_center_first_claim.py`（29ceaae 已装），本工具不自签、不领取、不写服务。

## 角色（Owner 已明确，不再找未知持钥人）
- 首次项目信任根托管/签发：小维ed43（保护宿主，唯一持私钥；开发端从不读私钥，只交换公钥 fingerprint/SecretRef 元数据）。
- 承接代码开发与测试：小开（developer，本仓库唯一 TC 源码 writer，base b638ffd）。
- 安装/执行上述命令：小维ed43；生产执行由小维，不由 developer 直写服务/DB。
- 核验：小审/小验（非作者）。三岗位 developer/independent-reviewer/product-acceptance-ai 必须各自有受信宿主 Ed25519 attestation；agent 名 JSON 一律不是认证。

## 实现（本仓库新增，未改任何既有 runtime 文件）
- `scripts/host_principal_bindings.py`：首次信任根 one-shot 生成（目录 0700、私钥 0600、拒绝重复 provision、输出仅公钥/指纹/路径）；principal/caller attestation 签发与验证（role 三岗位白名单、task 绑定、锚指纹绑定、Ed25519 验签、拒绝伪造/过期/重用；有效期只沿原协议"有限未来 epoch"规则——过去或无穷即刻拒绝，实际时长与续租值必须来自批准的原合同 grant，代码不自加期限）。
- `scripts/task_center_provenance_source.py`：真实受信 host principal 引用绑定，落已装 `GuardedProvenanceConsumer` 的 verify_login/current_provenance/assert_effect_current + principal mapper 协议（保护 config 0600：登录秘密摘要 + 每岗位签名 attestation；roles 只来自签名绑定，mapper 拒绝任何额外请求字段；宿主/config/锚文件轮换或过期即时失去 formal 态；不新建第二 session 权威）。
- `scripts/task_center_authority_handoff.py`：freeze（backup API 一致快照 + before manifest 每表行数/摘要 + effects 清单 + HMAC 有界冻结回执）→ handoff（校验 Owner 决定/锚指纹/三岗位绑定/caller grant≤原租约值；Supervisor+TrustedRegistrationVerifier **合法构造**新 FORMAL 目标（非复制重命名、非 SQL flip）；tasks 行 grant-free 不变量否则 SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED；FK 拓扑序承接授权的非授权 wiring 表；全部源行入 authority_handoff_provenance 带行级 sha256，digest 对账 before manifest；events/writer_*/resource_claims 等授权/会话/凭据表禁止承接；单事务提交回执，注入点回滚无残留）→ switch（单权威引用文件原子落位，旧测试视图只隔离标记不删除）→ reconcile（旧视图 switch 后任何写入 → TEST_WRITE_AFTER_SWITCH_DETECTED；目标 F4 正常写入如实报 TARGET_WRITE_EXPECTED_BY_F4）→ query/rollback（回执复核；回退只撤引用，不删数据）。

## 执行序列（小维在真实宿主，路径为受保护现物，秘密不进正文/模型/仓库）
```
PY=<现有venv python>  # 29ceaae 已装依赖专用 venv（crypto 42.0.8）；不重装
R=<release>/scripts
# 1) 一次性首次信任根（已准备则跳过并引用现有指纹）
$PY $R/host_principal_bindings.py provision-trust-root --root-dir /var/lib/xuanjun/tc-formal-activation/custody
# 2) 三岗位 + caller 签发（有限未来 epoch；expires 不得超过原合同租约真实值）
$PY $R/host_principal_bindings.py attest-principal --private-key-file <custody>/project_trust_root.key.pem --role developer --subject <真实subject> --tenant-id <真实tenant> --principal-id <真实principal> --task-id tc-real-development-20261123-4d99c26f2b07 --expires-at <原租约epoch>
#   同法 independent-reviewer / product-acceptance-ai（三个不同 subject/principal）
$PY $R/host_principal_bindings.py attest-caller --private-key-file <同上> --caller-id <真实caller> --run-id <真实run> --session-id <真实session> --gateway-id <真实gateway> --task-id tc-real-development-20261123-4d99c26f2b07 --expires-at <原租约epoch>
$PY $R/host_principal_bindings.py verify --anchor-public-key-file <custody>/project_trust_root.pub.pem --task-id tc-real-development-20261123-4d99c26f2b07 --binding-file <bindings.json|caller.json>
# 3) 冻结对账（停服务窗口：service_state=STOPPED, writer_state=NO_WRITER）
$PY $R/task_center_authority_handoff.py create-freeze --db $CANONICAL_DB --backup $EXCH/snapshot.sqlite --operation-id tc-handoff-1743 --trust-key-file <freeze.key 0600> --output $EXCH/freeze.json --manifest-output $EXCH/manifest.json
# 4) 承接构建 FORMAL 目标（decision.json 按 example 结构填 Owner 批准事实：approval 非 null、grant_or_lease_valid_until=原租约真实值、carry_over_tables=只列非授权 wiring 表且含 tasks）
$PY $R/task_center_authority_handoff.py handoff --source-db $CANONICAL_DB --backup $EXCH/snapshot.sqlite --freeze-receipt $EXCH/freeze.json --manifest-file $EXCH/manifest.json --trust-key-file <freeze.key> --decision-file $EXCH/decision.json --anchor-public-key-file <custody>/project_trust_root.pub.pem --bindings-file $EXCH/bindings.json --caller-file $EXCH/caller.json --target $NEW/canonical-formal.sqlite --operation-id tc-handoff-1743
$PY $R/task_center_authority_handoff.py query --target $NEW/canonical-formal.sqlite --operation-id tc-handoff-1743
# 5) 单权威引用切换（旧 TEST_ONLY 视图隔离，不删）
$PY $R/task_center_authority_handoff.py switch --pointer-file $EXCH/authority-reference.json --trust-key-file <freeze.key> --target $NEW/canonical-formal.sqlite --source-db $CANONICAL_DB --operation-id tc-handoff-1743
# 小维把服务配置壳（enabled=false 现物）指向引用文件所指 canonical-formal.sqlite 后才允许启用；启用后：
$PY $R/task_center_authority_handoff.py reconcile --pointer-file $EXCH/authority-reference.json --trust-key-file <freeze.key>
# 6) 同 task 签名 register 一次 → claim 一次（已装 F4 入口，不新造）
PYTHONPATH="$R" $PY $R/task_center_first_claim.py --db $NEW/canonical-formal.sqlite --mcp-development-config-file $PROTECTED_CONFIG --authority-key-file $PROTECTED_TENANT_KEY --task-id tc-real-development-20261123-4d99c26f2b07 --action register
# 成功后同参 --action claim 一次；响应未知只 --action status
# 回退（不删数据）：
$PY $R/task_center_authority_handoff.py rollback --pointer-file $EXCH/authority-reference.json --trust-key-file <freeze.key>
```
合同 `trusted_reviewers` 两条须等于小审/小验岗位 subject/key_id；canonical owner 别名保持 `developer`，其真实 Owner 映射记录在 decision，不当人名。

## 失败与恢复语义
- 全部拒绝走稳定错误码（FREEZE_EXPIRED/FREEZE_BACKUP_MISMATCH/FREEZE_DATABASE_STATE_CHANGED/FREEZE_MANIFEST_MISMATCH/DECISION_*/HOST_PRINCIPAL_*/HOST_CALLER_*/CALLER_LEASE_EXCEEDS_APPROVED_GRANT/PRINCIPAL_LEASE_EXCEEDS_APPROVED_GRANT/CARRY_OVER_TABLE_DENIED/CARRY_OVER_FK_CYCLE.../SOURCE_TASK_GRANT_HISTORY_RECONCILIATION_REQUIRED/PROMOTED_TEST_AUTHORITY_DETECTED/PRESERVATION_INVARIANT_MISMATCH/PROVENANCE_ROW_TAMPERED/HANDOFF_RECEIPT_*/TARGET_OCCUPIED_OR_INCOMPLETE/TEST_WRITE_AFTER_SWITCH_DETECTED/AUTHORITY_REFERENCE_*）。
- 注入点崩溃：事务回滚，目标内无任何 handoff 表；处置=删除未提交目标 staging 文件（无权威制品）后按同一 operation-id 从冻结检查点重跑（freeze 未过期则复用）。
- 回执已 COMMITTED 的重放=返回同回执；异 operation 指同目标=TARGET_OCCUPIED_OR_INCOMPLETE。
- switch 后旧库出现任何写入=TEST_WRITE_AFTER_SWITCH_DETECTED：停，先对账，不回滚脚本自动处理。
- 代码回退/引用回退不等于数据回滚；已产生的正式 register/claim 保留供对账（沿原防回归要求）。

## 证据
- `tests/test_modern_authority_handoff.py` 13 例 + `tests/test_host_principal_bindings.py` 8 例，21 OK（../python-env/.venv Python3.11.2+cryptography42.0.8，同版复用不重装）；含正例端到端：同 task 在承接目标经已装 F4 完成 register+claim→RECEIVED（fixture 隔离，非真实任务已领取）；负例：伪签名/agent名JSON、过期/caller超租、profile flip 决定、授权表承接、源含 grant 历史、快照篡改、冻结过期、源漂移、provenance 篡改、switch 后写检测、注入回滚+断点续。
- 原 F4 7 例 + legacy 迁移 10 例=17 OK 回归不破（未重跑全套 27/12 旧安装链，按 delta 必要定向）。
