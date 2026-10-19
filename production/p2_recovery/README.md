# P2受控恢复执行接线

原任务PR17，继承d0929def的恢复证据门禁及6041c745运行核心。英国FIRST_DEPLOY不重跑。英国未执行本增量；PRODUCTION_ISOLATION=WAITING_REAL_EVIDENCE，P2_RELEASE=HOLD。

## 本轮实际执行入口

production/p2_recovery/entry.py提供apply、serve、run正式入口。bootstrap.py只按显式SHA、受保护文件描述符加载代码。executor.py将恢复证据、真实管理Provider、原Registry、AuthorityStore、Issuer及原PermitCycle接线。原production/p2_attempt5/entry.py对恢复Grant(recovery_entry=p2_recovery.entry)增加强制恢复Gate；历史普通Grant入口保持原边界。新增apply强制要求此恢复Grant标识；不支持用CLI布尔值或环境变量绕过。原16阶段、Ledger、IssuerService、AuthorityStore、NativeRecovery、授权HTTPS校验与原生锁代码不改。

apply不会启动Writer、服务或16阶段。serve/run首先核对已持久提交的恢复回执、数据库inode及新权威来源；随后仍执行原Registry、Grant准确Commit/Tree、Kit和完整Assembly Manifest校验。Issuer构造、每次接收及真正handle前、原生RPC与Driver.check_binding均重新查询隔离和对账状态。保留具体Driver、原生锁及Fence，不跳过阶段。实际副作用入口仍必须在Provider所证明的统一控制面落实Fence；本地检查不能替代跨系统原子排他。

## A/B执行与失败恢复

A只接受原管理执行器形成并三方签名绑定的一致性备份，绝不复制未知活库或忽略其WAL。向O_EXCL新恢复目标复制全部备份字节，原件不变；保留所有表、Grant消费数、Attempt、proof及Audit。旧Grant置terminal、旧租约失效、旧cycle停止，变更前完整状态另记Audit，新Grant必须由原Owner准确HTTPS授权认证，新Epoch/Fence在第一份Lease严格推进。恢复目标有独立新权威来源，不能宣称它就是原库。旧事务处置与安全恢复检查点仍需管理方可信对账，UNKNOWN拒绝。

B只在UNRECOVERABLE_WITH_DISPOSITION、旧权威可信隔离及历史副作用处置成立后调用原AuthorityStore(initialize=True)。不存在任何“未找到即首次初始化”的捷径。新Grant独立身份，最多5次持久消费，原独立授权正文及编号不逐次改变；旧Grant不能自动重放。原库、WAL、备份和回执不改。

apply在现存root0700检查点目录取得独占锁。AuthorityStore目标及sidecar、issuer锁任何已存在状态拒绝覆盖。数据库、Grant、cycle及新权威来源落盘后登记原Registry，再写O_EXCL恢复回执、fsync文件/目录，最后通过SQLite FULL独立提交索引发布。serve/run只读核验该提交，不自动补登记。提交成功后进程重启可幂等再入，不重置额度。历史三签包只作为已签名请求/plan/备份配方，不能作为当前许可；即使原5分钟证据窗口已过，正式入口仍可自动向真实Provider取得新鲜nonce/时限/三签隔离及对账证明，Grant仍须有效，审核ID及批准正文不改变。新鲜证明缺失或恢复快照变化时HOLD。未提交的数据库或回执保留并HOLD；不能删除后重试或自动采纳。失败恢复需管理Provider先对新恢复副作用作可信对账，当前版本对这种未提交输出不自动续写，属于明确保留的人工恢复边界。

## 真实管理Provider接口（客户端已实现，英国部署未证实）

管理执行器通过显式配置的root0600 Unix流式socket提供接口；父链root保护且拒绝符号链接，SO_PEERCRED必须uid0。4字节网络序长度+canonical JSON，最大262144字节、单次5秒。请求严格为schema=1、operation、request_sha256、challenge(随机32hex)。operation=recovery_apply要求原控制面持久、原子地按旧权威隔离范围保留唯一新权威，重复同request_sha256/plan_sha256幂等返回原保留记录；冲突必须拒绝，断连UNKNOWN后不得切换新ID；operation=execution_gate要求核对/续接同一排他绑定，不能另建Writer。

响应body/signatures，body严格为schema、probe(完整原请求)、issued_utc、expires_utc(最多30秒)、packet、reservation。owner/isolation/reconciliation三把既定且不同的公钥均验证完整body签名；packet也必须满足原三签恢复证据协议及完整历史对账，sources包含准确plan引用。reservation严格绑定old_authority_id、authority_id、epoch、fence(与新Epoch相同起点)、writer_id、grant_id、database、plan_sha256及exclusive=true。UNKNOWN、失效租约、冲突、断连、旧nonce或签名错误均拒绝，不能缓存旧成功答复。

本仓库不附带声称已撤销英国凭据的模拟生产Provider。测试socket服务使用真实RSA、真实Unix协议及真实SQLite，但所有主机隔离事实均为SYNTHETIC_TEST_ONLY。Owner/isolation/reconciliation是管理证据签名职责，不是重新引入Dots逐次许可。

## 准确执行配置与现场交付

apply-plan必须被原恢复packet.sources准确签名引用；字段schema、request_sha256、config(path/sha256)、registry_record(path/sha256)、registry_root、assembly_manifest(path/sha256)、assembly_root、kit_root、loader_sha256、kit_manifest_sha256、provider_socket、checkpoint_root。私有配置仍用原格式，Registry来源记录仍绑定Issuer公钥、Adapter、AuthorityStore及Writer/Fence。配置原件、真实NativeAdapter binding、Signer及旧事务plan/seed不从候选路径推断。所有目录须预先受保护；程序不chmod/chown、不创建目录，不生成私钥。

新Assembly版本由build_apply.py绑定准确Commit/Tree及全部依赖，继承英国现存6041版Kit和原Manifest SHA；新增恢复代码及正式entry变化由新Assembly Manifest和新Grant绑定。旧制品及冻结文件保留，不覆盖。build.py只生成原证据模块范围的制品，不作为新执行Assembly使用。

英国尚需一次性落实：
1. 原SSH/RAM、Runner、systemd、scheduler、Issuer API、storage clone及其他主机全部写入来源的实际撤权/排空/旧Epoch拒绝；inactive不能替代撤权。
2. 在同一真实控制面保留新authority_id/Epoch/Writer/Fence，接通上述provider_socket协议；必须拒绝另一恢复请求并行建立第二权威。
3. 完成原Run/Job/InvokeId、16阶段事务副作用、备份检查点及历史Grant/Attempt对账；A交付一致性备份，B交付无法恢复及历史安全处置证据。
4. 通过原Owner通道固定三把管理公钥及trust摘要、准确apply-plan、真实Signer/Adapter配置和新版本Grant绑定，不公开私钥。
验收：独立实际撤权反向测试拒绝旧身份/旧Epoch；Provider对冲突及UNKNOWN返回拒绝；apply回执与数据库/Registry/持久索引一致；serve/run只在真实Fence和事务条件成立后执行。以上未实证前，不生成含猜测参数的英国激活命令。

## 测试范围

新增32项受影响测试覆盖正式apply命令、原Artifact12142409951中的准确Kit字节(不按其他Python/zlib重压缩)、严格Inventory、原Owner授权验证、真实RSA/socket、三签nonce、A/B、旧历史保留、旧Grant拒绝、5次额度/成功停止、重启、并发/部分输出、审批缺失、Fence/UNKNOWN、源码变化、正式Issuer签名RPC及正式入口强制Gate。原951项不重跑；未变核心逐字校验。Hosted CI不是英国验收。

---

以下保留d0929def原证据协议和检查点设计记录（其中“本模块”仅指recovery.py，而不是新增executor.py）：

# P2受控权威恢复增量

原任务PR17。运行基线6041c7458dce7c83c49c5a9eafa0e20cef52d1c0 / Tree 8e27d077d22af392108568ac06d284df4dd4b35e。已有英国Kit/Assembly及Registry目录原样复用。不修改原951项、175项已通过源码，不涉及PR99、PR122、东京或资金系统。

## 已实现与明确边界

recovery.py提供正式assess/checkpoint命令，校验独立管理来源签名，形成有期限、准确版本及请求绑定的恢复决策，checkpoint持久发布经过文件fsync、目录fsync及SQLite FULL元数据事务。没有initialize/register/activate命令，不打开生产AuthorityStore、不创建生产密钥、不发Grant、不调16阶段。决策成功只叫RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED，不能替代安装准入或真实隔离动作。

这是原部署管理链丢失后的新增恢复准入模块，不是再次搜索“从未部署”的证明。旧历史无法取得时，B路线允许在隔离和副作用处置证据成立后提出新权威；新权威ID、新Epoch、唯一Writer ID和新Grant ID明确与旧权威分开。原库UNKNOWN不能因为还有额度而绕过。证据程序不签发首次部署资格、不认定历史不存在。

## 旧权威隔离与来源

必须由Owner固定的三类管理公钥分别签署同一证据正文：owner、isolation、reconciliation。三把公钥DER摘要必须不同；公钥原件root0600、逐父链root保护且无ACL。信任JSON自身的准确SHA由原受信Owner执行通道固定；不能从证据包自带公钥推导信任。生产代码没有私钥生成或fixture分支。所有签名用RSA2048–4096/e65537/SHA256，OpenSSL验证。

证据必须覆盖八类潜在通道：ssh、ram_swas、github_runners、systemd、schedulers、issuer_api、storage_clones、other_hosts。每类有实际source_id、隔离/不存在证明回执SHA；UNKNOWN、仅STOPPED、未涵盖的外部Writer和不完整清单拒绝。该枚举是最低分类，不是代码自动发现全世界Writer；完整性由原基础设施管理方的准确范围和原件背书，任何不能归入清单的外部通道应列unknown_writers，不允许默默省略。

管理动作应在原控制面落实：回收旧执行主体的写入资格和旧Grant、使原副作用入口拒绝旧Epoch/Fence、排空原调用并核对InvokeId、阻止旧Runner/定时器恢复领取、隔离可写存储克隆及其他主机。服务inactive或本机flock不证明跨主机失效。本模块只验证这些动作的可信回执，不声称已经执行云权限、SSH身份或原事务的撤销。不借用其他项目身份，不解除已有mask，不启动Runner。

## 证据协议

请求字段严格固定：schema=1、host、source_commit/source_tree(固定原运行版本)、recovery_id、old_authority_id/new_authority_id、old_epoch/new_epoch(严格增加)、writer_id、new_grant_id、route、target_database、nonce(64位小写十六进制)。旧权威未知时不可编造old_authority_id/Epoch；这是仍需现场管理资料或受信隔离体系确定的外部输入。target_database是决策目标，程序不会访问或创建它。

包为body/signatures；正文包含schema、request_sha256、issued_utc/expires_utc(最多300秒)、inventory、isolation、history、sources、restoration。三签名均覆盖canonical ASCII JSON完整body。准确请求含主机/新旧权威/版本/nonce，不能复用旧包批准另一请求。sources是已保管原件path/sha256数组，逐一读取并校验，仅输出摘要。isolation要求all_old_tokens_rejected=true、旧ID/Epoch准确、revoked_grants_sha256和enforcement_sha256；history要求RECONCILED、无pending_transactions/unknown_effects、old_grants_not_reissued=true，并保留数据库及sidecar、备份、执行回执三类来源证据。布尔值必须来自已签名管理证据，不能据服务停止本地产生。

A RESTORE_EXISTING：restoration.status=CONSISTENT_BACKUP_VERIFIED，snapshot为由原管理执行器已创建的一致性备份的path/sha256。此模块不生成快照，不对未知活库使用immutable忽略WAL。先校验受保护备份原件与SHA，再复制到root私有临时目录只读检查，原件逐字保留；SQLite quick_check/schema/Grant及ordinal连续性/最多5次/UNKNOWN检查失败即HOLD。该核验不构成全部业务Audit语义完整性证明，原事务/备份来源及副作用由可信reconciliation签名负责。恢复必须回到原唯一库并保留全部表、Grant/Attempt/Audit与原额度；本模块不导出重建一份库。已有SUCCESS不可重跑，额度不清零。

B NEW_AUTHORITY：restoration.status=UNRECOVERABLE_WITH_DISPOSITION且snapshot=null；此状态由管理方提供明确依据，不由本模块从“未找到”推断。必须先满足相同隔离、无未知副作用及旧历史安全处置条件。后续创建仍需专用受控初始化动作、唯一新权威来源登记和服务端每次调用的实际Fence约束；本模块不能替代它们。旧Grant不得在新库重新注册，新的Grant需真实Owner认证，不能自行伪造准确批准正文。

## 持久检查点及失败恢复

assess不创建持久文件；签名验证及备份核验会创建并清理/root内只含公开签名/公钥或一致性快照的私有临时目录，不能描述为零文件系统副作用。checkpoint只写显式既有root0700 recovery checkpoint目录，不创建根。它的.recovery-commits.sqlite3只存决策摘要和inode，不是生产AuthorityStore，不含Grant余额，也不能作为唯一Writer证明。

准确recovery_id.json以O_EXCL/root0600写入并fsync，目录fsync后才以独立SQLite FULL提交发布。部分写入/目录同步失败无提交行，原输出保留，重启或重试不得补认成功；已提交同内容可幂等读回。冲突/链接/硬链接/目录不受保护/未决metadata journal拒绝。不删除数据库或WAL/sidecar，不自动恢复meta索引，不因进程重启重置任何Attempt。每次正式入口仍重新认证签名和有效期，旧持久决策不是无限期执行许可。

## 英国执行与剩余管理操作

当前英国没有本恢复增量，不重跑FIRST_DEPLOY。源码和CI不等于现场隔离。

Owner/基础设施管理方最小操作：
1. 指定原受信管理通道中可执行旧权威隔离及副作用对账的实际身份，固定三类公开信任摘要；不公开私钥。
2. 在原控制面完成八类通道排空/隔离和原InvokeId/副作用对账，保留原数据、WAL及备份。未知通道必须显式保留为阻塞。
3. 通过该通道交付与本次nonce/新旧Epoch准确绑定的三签名包及来源原件。若原库恢复则供一致性快照；无法恢复需明确disposition依据。
4. 只有包校验成功，才可制定新Authority初始化/原库继承、真实Signer/Registry binding和最终16阶段执行。现在不生成猜测值的英国activate命令。

本轮可以交付准确、无占位符的源码自检命令，但不能给出可实际通过的生产assess/activate命令：真实信任SHA、证据原件路径、旧权威ID/Epoch尚未提供。调用者不能把测试密钥/合成证据带到英国。没有后台生产任务。

41项新增测试使用真实RSA、root隔离目录、SQLite和子进程，所有管理事实明确SYNTHETIC_TEST_ONLY；不是生产验收。旧底层代码/CI限定结论继承；本模块尚未接入serve/run，所以不得声称已恢复生产安装能力。新建Authority/Grant/激活入口仍待可信现场隔离Provider及恢复执行范围落地。本增量先完成能独立实现的证据准入和持久检查点，避免再次将管理员口头前置当作已实现的生产动作。

另在明确SYNTHETIC_CONTAINER环境中设置固定UK hostname，真实独立-I -B -S CLI执行assess、checkpoint、跨进程幂等确认和过期拒绝；无host验证绕过或生产fixture参数。容器名称不冒充英国真实主机。

### Management Provider service (production bridge)

`provider_server.py` now implements the root-only framed Unix service used by
`UnixEvidenceProvider`. Its only operations are `recovery_apply` and
`execution_gate`. Both client and server use the same exact signature, challenge,
source, plan, restoration, lifetime and reservation validation. Invalid or
UNKNOWN evidence cannot create a reservation or reach AuthorityStore apply.

The service uses an explicitly initialized **management reservation journal**,
separate from AuthorityStore. `serve` never initializes a missing journal. A
process-lifetime flock prevents a second local service. SQLite FULL transactions,
unique old/new authority, database and Writer bindings, and an append-only audit
allow exact request reentry after a lost reply or restart. Conflicts are rejected
before calling the management adapter. A directory fsync failure suppresses the
reply even if SQLite already committed; retry must use the identical request.
An existing socket is never unlinked automatically: after a crash, the manager
must verify the original process/lock and remove only its stale socket under its
existing controlled recovery procedure. Database and sidecars remain intact.

The `initialize-reservations` CLI only creates a new marked management journal
with O_EXCL; it does not create an AuthorityStore, keys, Grant or Writer. No such
initialization or service deployment has been performed in the UK. CLI requires
isolated root Python, the fixed UK hostname, and accurate bootstrap/recovery/
executor pins. `serve` additionally requires exact request, trust, evidence,
plan and adapter file/SHA bindings. The signed plan supplies the socket path.

The adapter is a protected, SHA-pinned Python management integration, executed
with isolated Python, no shell, a minimal environment, bounded output and a
four-second deadline. It receives `P2_MANAGEMENT_REQUEST` containing `probe`,
`request`, `plan` and `restoration`; it must return the existing signed Provider
response. It must query the real control plane, including global exclusive
reservation and real transaction reconciliation. Repeated readback/renewal must
be idempotent under the exact request identity. A timeout is UNKNOWN, never
proof that a remote action failed. Raw errors and private configuration are not
returned to the caller. The service does not generate facts, sign on behalf of
three roles, revoke unknown credentials, or turn local flock into global fencing.

**External binding remains required:** an actual deployed management adapter,
three independently pinned public trust identities, and real old-channel
revocation/global reservation/transaction readback evidence. The new server
provides the production protocol and durable local coordination, not proof that
these external controls exist. Test adapter signatures and isolated socket/SQLite
results must never be submitted as UK isolation evidence.

Affected acceptance adds real signed backend positive/negative cases, journal
restart/reentry, fsync failure, conflict-before-query, signature/fence/UNKNOWN
rejection, adapter bounds/timeouts, and a real service process → real adapter
process → existing recovery apply → committed gate integration. Tests use
synthetic management facts and keys only; original reviewed business logic is
inherited. UK activation and sixteen stages remain NOT_EXECUTED.

### P2 control-plane functional nodes

`control_plane.py` is the native management adapter, selected by the existing
Provider CLI using `--control-config`, its SHA and `--control-code-sha256`.
`register-control` registers an exact Owner-signed configuration and revokes the
old authority/Epoch in the **existing shared management journal**. It creates no
AuthorityStore, Grant, private key or Writer. `serve` uses that committed binding;
there is no need for an arbitrary external adapter program in native mode.

1. **Managed-channel revocation:** eight exact channel categories, principal
   lists and original enforcement references are bound to a three-role signed
   inventory and original recovery packet. The journal records the revocation
   scope; unknown external channels cannot pass admission. This does not revoke RAM
   credentials or SSH access by declaring a row: those external revocations must
   be carried out by their actual management authority and independently proved.
2. **Epoch/Fence denial:** `ControlPlane.enforce` rejects the old authority through
   its revoked Epoch and admits only the exact new authority/Epoch/Writer/Grant.
   All participating executors must use the one deployed Provider entry. Old
   binaries that bypass it remain external Writers and require real isolation.
3. **History reconciliation:** `transaction_snapshot` reads only an exact,
   already-consistent manager backup through the inherited snapshot validator;
   retains Grant consumption, Attempt ordinal/state/proof and audit digest.
   `invocation_state` reuses the original SWAS RPC interface for
   DescribeInvocationResult only. InvocationResult/InvokeId/instance/status are
   checked. Cloud Success is NOT a transaction outcome. The signed invocation
   inventory must exactly equal the signed terminal/reconciled receipts, each
   tied to a preserved transaction source. Missing, pending or UNKNOWN is HOLD.
4. **Shared exclusion:** reuse original Provider Reservations, unique shared
   authority/database/Writer rows, process lock and exact request reentry. No new
   parallel authority/quota ledger. All executors must query the single shared
   deployment; independent copies are NOT global exclusion proof.
5. **Trust/config:** root-protected SHA-bound config, independently pinned three
   public keys, Owner-signed config digest and matching existing private Signer
   descriptors. No generated production keys, secrets or public trust defaults.
   File/directory fsync precedes the final FULL SQLite registration publication;
   failure cannot authorize a later serve after restart.
6. **Provider integration:** shared validation and challenge protocol preserved.
   Native control signs the fresh challenge with the bound real keys only after
   checking current original evidence. It never refreshes expired evidence or
   converts local policy into a new historical isolation assertion. Durable
   reservation/audit commits precede the returned signed response.

**Production acceptance, one condition per node:** (1) actual eight-category
inventory and external revoke/readback originals, (2) old-token rejection at
EVERY actual side-effect entry, (3) preserved original backup plus complete
Grant/Attempt/InvokeId/side-effect closure, (4) two real executors competing at
the same service yield exactly one authority and conflicting request rejection,
(5) original trust provenance/private configuration sealed at exact SHA with no
secret disclosure, (6) deployed formal register-control/serve/apply gate returns
real signed receipts. None of these UK production results has been executed by
Hosted CI. Unknown external Writers keep production HOLD.

Deployment inputs still required from the actual UK executor: protected new
control-config and Owner-signed digest, existing three trusted key references,
fresh signed inventory/evidence, completed external revocations and all relevant
InvokeId/transaction receipts. Do not use synthetic tests as these inputs. No
FIRST_DEPLOY, Prepare or new RAM authorization is needed for the offline changes.

Within a registered control configuration, `live_evidence_path` is the single
Owner-approved protected refresh source. Fresh three-role signed evidence can
replace that file without changing the Grant, config digest or Owner approval.
Every read revalidates signatures, exact request/plan/restoration, current expiry
and all signed source hashes. The inventory source path stays approved while its
current SHA must be present in the fresh signed packet. The installation entry retains its separately pinned historical bootstrap
recipe; the control configuration binds `plan_sha256` and the live source path. A locally edited
timestamp or expired original cannot become fresh evidence. This preserves
ONE_PERMIT_MAX_5_ATTEMPTS without requiring a new configuration approval for
every safe continuation; no source/scope/Signer change is authorized by refresh.


Local control enrollment is deliberately separate from production admission.
`register-control` may install the Owner-signed P2 deny policy before external
isolation has been proved; it uses the pinned request/plan/trust and creates no
reservation, AuthorityStore or Grant. This avoids requiring old-token rejection
proof before its server-side rejection policy can be enrolled. `serve` still
requires the original signed recovery recipe, and every `respond` requires fresh
complete evidence. An enrolled policy is never an isolation or activation PASS.

`control-status` is an authenticated-root, digest-only policy query. It reads the
committed Owner approval source again and reports only enrolled local denial and
configuration/trust hashes. It explicitly returns production_admission=
NOT_EVALUATED and external_isolation=NOT_INFERRED; it never signs or promotes a
policy query into an external isolation receipt, consumes quota or starts Writer.
The original Owner signature reference is persisted and rechecked after restart.
