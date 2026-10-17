# PR99 剩余服务接续执行顺序与验收账本（2026-10-16）

本表是实际三机采样后的执行准备，不是运行迁移PASS。原PR99原分支继续；API延后重建，不新增API/交易上线前置；不重复已通过资产与环境。

## 本次当前恢复点真实执行（2026-10-16 晚）

Owner在韩国通过sudo-root完成许可#6217030577的一次R2执行，终端返回`CURRENT_OFFLINE_POINT_RECEIVED_PASS`。原1363文件匹配，WAL-aware SQLite恢复副本integrity_check PASS；目标`/root/pr99-current-point-received-v2`。数据库SHA`6d451dfdc4714ca9bc704d719dcb47b02ec1e2ce243f886bfb2578a27fbca232`，密文SHA`2ac42b9e69c69260c99387b2e1ae339dd2e80b3f01c1984858e458e6c8872d32`。这是Owner-root回执支持的真实执行，不是审核窗口直接读取私有原件。原V1失败现场保留；成功R2不得重跑。未冻结Writer、未部署生产、服务动作0、API请求0。R2执行回执已由独审#6217422554限定接受；不升级为独立私有数据库复算。

## 最新原始证据

Run38904470291，提交e4dfdf03a246fd911a226d911970854d2606328e。国内Job116984492029、东京Job116984492318、韩国Job116984492559均SUCCESS。三机UID1002/1001/1001，只读systemd属性和选定监听端口，无checkout、sudo、进程参数、unit内容、私有配置、凭据、数据库或HTTP读取，无服务动作。原20/22/134及既有主机检查全部SKIPPED。

最初workflow e788db355d33d105268c986769317baed8d02f13 / Run38904433601因YAML矩阵表达式未加引号解析失败、jobs=[]，没有主机执行。已在上述准确提交修复；不是重试任何失败生产操作。保留失败记录。

## 十个节点的准确终态

| 节点 | 已有成果 | 尚缺的结束条件 |
|---|---|---|
| S01 任务/目标和旧API范围 | 原PR99、双机固定身份、API延后、旧通道保护已固定 | 不扩大为默认停机权限 |
| S02 异机备份及密钥 | #6215371855限定通过，历史密文与恢复密钥在韩国 | 不重复传输，不冒充当前数据 |
| S03 历史恢复和依赖环境 | 历史1374文件、13项依赖和pip/import验收已通过 | 不重装历史环境 |
| S04 当前源文件身份 | 服务器1363文件19,350,718字节逐文件摘要已取得 | R2已按原服务器摘要复制1363份选定源码；原清单含436份历史backup，不冒充全部当前应用闭包 |
| S05 当前SQLite恢复点 | 原20项继承，R2新增7项通过；#6217030577批准后Owner-root一次执行成功 | 离线恢复点已由#6217422554限定接受（Owner-root证据），不是交易final checkpoint |
| S06 生产目录与运行合同 | 10份unit、1份drop-in及私有元数据已按#6218349901接收；Owner-root成功回执；旧失败现场已保留 | 私有当前配置、运行用户/目录/端口/数据绑定、受控候选与回滚批准；不能整包恢复/etc |
| S07 客户网站动态入口 | 国内静态网站原通过；东京Portal/WeCom仍在运行，国内同名unit不存在 | 国内逐服务接续、真实非写验收、入口上游切换与回滚；不得用历史Portal覆盖R4 |
| S08 模型/RPC/小说/VPN通道 | 三机端口和systemd依赖关系已取得 | 私有配置/证书身份、双端通道与客户端指向验证；UK既有P2由原writer负责，本分支不恢复UK |
| S09 调度与最后增量 | 东京四财务timer实际active；未知root/admin cron已明确登记 | 定时任务保留/迁移/停止的明确决策、私有cron核查、最终数据时点和单Writer安排 |
| S10 正式接续/退役 | 尚未执行 | 全部保留职责已接续或明确取消，验证回滚后再单独批准东京退役；东京继续运行 |

S04/S05本次批准范围内的真实离线复制已完成；不等于1363选定文件覆盖全服务器，也不等于最终Writer数据切换。当前进入S06运行合同与私有通道交接，S07—S10仍未完成。S01—S03已通过历史范围继续继承。

## 服务接续依赖与落点

目标沿既定架构：国内承接网站/客户入口，韩国保留币安离线运行资产与已有小说运行环境，英国开发控制和模型执行由原P2链处理。以下是接续落点，不是已安装声明。

| 职责/当前unit | 本次实证 | 接续顺序与完成证明 |
|---|---|---|
| Portal secure-secrets-portal | 东京active PID3082952，cwd/opt/trading-system；国内同名not-found | 先形成当前源码和必要私有运行材料；国内新隔离候选沿用R4；只读拒绝/健康/上游验证后再修改入口，不停止东京先求测试PASS |
| 客户联系 xuanjun-wecom-customer-contact | 东京active；After包含Portal；国内同名not-found | 国内Portal就绪后接入客户联系；私有身份/回调材料不公开；不以真实客户消息作测试 |
| 客服 xuanjun-wecom-customer-service | 东京active；After包含Portal、provider-neutral-tunnel；Wants provider-neutral-tunnel | 必须核实该精确unit/别名身份，不能把provider-neutral-tokyo-tunnel自动当成同一对象；国内接入后才切回调 |
| 旧小说入口 xuanjun-wecom-novel-ingress | 东京active；Wants korea-novel-model-rpc-tunnel | 韩国已有novel-factory active、cwd/opt/xuanjun-novel-factory/app，不能覆盖该共享实例；保留入口/通道所需内容与回滚，小说功能扩展不加入本批 |
| 国内模型隧道 domestic-model-rpc-tunnel | 东京active；Requires tokyo-restricted-model-executor | 先替代执行端，再改隧道客户端依赖；不能只搬SSH脚本后关闭东京模型端 |
| 韩国小说模型隧道 korea-novel-model-rpc-tunnel | 东京active；After模型执行器；Requires未声明模型执行器 | After仅排序而非存活保证，单独验证上游和失联行为；不以systemd active当端到端PASS |
| provider-neutral-tokyo-tunnel | 东京active；国内bridge active PID188767、cwd既有internal-bridge | 国内18443和19444正在监听，东京19443正在监听；本采样没有证明每个端口的具体PID/流向或认证等价，不从端口号推定已切换 |
| restricted-rpc-openai-shim / tokyo-restricted-model-executor | 东京均active；executor有provider-health-alert.conf drop-in | 私有交接必须包含准确drop-in、身份和运行材料；本次没读内容。与原UK P2 writer明确交接，不能在本分支恢复UK mask或启动第二writer |
| xj-tokyo-vpn | 东京active且Requires docker；docker active | 需要容器/网络/访问端的独立受控接续；韩国tailscaled active仅证明进程存在，不证明VPN用户已迁或可替代东京容器 |
| Binance运行资产 | 韩国B inactive/PID0、PrivateNetwork=yes；当前恢复点R2已接收，S06运行接续未完成 | 本轮只做离线资产，原B和current不改变；未来交易启动另行验证唯一Writer/对账，不能拿API延后当批准 |

后续S06 Owner-root回执已确认韩国443归属morelogin-socks5-permanent.service（gost PID996/root），不得占用、改写或重启该共享服务。19444归属sshd PID1283/UID1000，未证明其具体远端或systemd单元。任何未来部署前必须核实所属者。更多自定义服务、用户级进程、容器和cron尚未穷尽，本次不是完整服务器职责闭包。

## 四项财务调度逐项保留

| timer | 最新状态 | 当前动作 |
|---|---|---|
| finance-collection-sync.timer | loaded/active | 保留东京，不执行或改触发器 |
| owner-commercial-ledger-sync.timer | loaded/active | 保留东京，不执行或改触发器 |
| billing-operations-weekly-settlement.timer | loaded/active | 保留东京，不执行或改触发器 |
| billing-operations-weekly-final-invoice.timer | loaded/active | 保留东京，不执行或改触发器 |

这不是完成财务迁移或Owner已接受丢弃其状态。关闭东京前必须明确处理。韩国已存在的yibi-api、yibi-scheduler、postgresql、redis、morelogin、novel、tailscale均只采样不操作；不为本次搬迁新增易币开发或碰现有共享实例。

## 下一次现场批的必要输入（集中获取，不逐字段找Owner）

1. S04/S05批准复制已成功，提交Owner-root回执做一次执行验收；不重复复制、测试或审核原源码。
2. 独立的私有通道材料采集合同：准确unit及drop-in清单、应用入口/依赖、非API通道身份、双端连接关系、端口所属者、root/admin cron脱敏闭包；敏感材料仅加密私有传递，不入GitHub。
3. 由同一批材料生成国内新候选及明确回滚路径，固定既有Work/current/桥接/共享服务前后快照；不假装本次非root属性是root安装验收。
4. 为实际新安装和上游切换提交一次集中范围裁定。未变的B/C、旧20项测试、官网/HTTPS/R4不再审核。

当前复制许可已消费且成功。本分支仍没有任意root终端，既有固定通道不包含任意私有配置读取或服务切换；不能扩大旧许可。能在当前GitHub通道完成的采样/证据/准备继续推进；需要真实私有数据或服务切换时保留准确阻塞。


## S06 新增实际采样

Run38913529642，提交69eeefabee15fcacc8b0d5deb0fc287898d56b27；三机三个Job全部SUCCESS。完整证据见`evidence/pr99-service-handoff/RUNTIME_METADATA_20261016.json`，下一批边界见`evidence/pr99-service-handoff/S06_PRIVATE_HANDOFF_CONTRACT_20261016.md`。本次确认东京generic provider-neutral-tunnel unit为not-found，不能当作Tokyo命名unit的别名；韩国443归属仍受非root权限限制UNKNOWN，不能盲占。国内site-hub-preview属于其他writer，保护不动。Root/admin cron及其他用户/proc详情仍UNKNOWN，不扩展为root验收。没有服务安装、启动、重启或配置改写。


## R2验收关闭，S06新候选已形成

独审#6217422554已认可R2 Owner-root离线复制回执；S04/S05在该限定证据范围通过，禁止再用#6217030577重跑。下一批S06候选准确源码4c9460a215b793259228f9d2e0fbfe5ea50267a1，Hosted Run38916022943/Job117023586355新增19/19 PASS，原历史测试未重跑，全部生产Runner SKIPPED。候选仅10份unit、1份drop-in及私有运行元数据一次加密交接，不读取EnvironmentFile/Token/SecretRef或数据库，不安装或改变服务。unit原件可能内联认证，全部保持root私有，不可宣称凭据内容绝不存在或上传GitHub。新动作PR99_S06_PRIVATE_RUNTIME_CONTRACT_V1需另行准确许可，原R2许可不能代替。完整API/运行秘密、容器/调度闭包及服务接续仍不冒充完成。


## S06真实私有采集成功（2026-10-16 23:14 Owner消息）

替代许可#6218349901已执行一次，原脚本SHA9ca936d3935732c0b4161f7599286ed63a022a142cb1e6cac69601f64bfb9eca未改。Owner终端报告TOKYO_ROOT_PREFLIGHT=PASS、SOURCE_STAGE=ABSENT、OLD_FAILURE_ATOMICALLY_PRESERVED，随后返回S06_PRIVATE_RUNTIME_CONTRACT_RECEIVED_PASS。准确回执见`evidence/pr99-service-handoff/s06-candidate/OWNER_SUCCESS_20261016.json`。原失败目录保存在`/root/pr99-s06-runtime-received-v1.auth-failed-6217834919`，成功材料在原v1接收目录；两个许可均已消费，不再重跑。

10份unit、1份drop-in及1份私有元数据已加密私有接收；archive SHA ec11ca6f579beb681adfd739bfeca5b836a22812676fd86a298340913c5243fd，cipher SHA d9bb83a859e0bfc307890539aa22ed872d9ab51c63db79a63f1e5cbeaa683e06。没有EnvironmentFiles读取、数据库读取、业务API请求或服务操作；unit可能内联认证，原件和密钥不公开。证据是Owner-root执行回执，不是开发方/独审方重新登录后重算私有原件。

韩国443的UNKNOWN已由本次Owner-root采样关闭为MoreLogin gost PID996/UID0；这只解决端口所属者，不等于任何新服务安装可占该端口。19444为sshd PID1283/UID1000，通道端点/认证及最终责任仍需核实。

下一步直接使用已接收材料形成脱敏的运行入口/路径/依赖清单和S07/S08候选，不再采集或重传上述11份配置、不重跑19项测试。已收集配置尚未等于生产迁移：EnvironmentFiles、实际通道身份、容器、root/admin调度、目标目录/账号/端口和回滚仍未闭包；不恢复API、不启动交易、不动Finance或UK/P2。剩余服务落点与受控安装/切换另行准确批准，东京继续运行。


## S06已独立限定验收，现成副本投影已成功

独审#6218862352直接接受#6218740070中的Owner-root执行回执，旧S06采集和19项测试继承，不再重做。Owner随后在韩国执行fbbfc6a7投影，返回RECEIVED_CONTRACT_PLANNING_PROJECTION_PASS；实际公开选定字段见`evidence/pr99-service-handoff/s06-candidate/OWNER_PROJECTION_20261016.json`。本投影不是独审批准的新生产安装，不扩大为服务已迁移。

真实已绑定：18080归Portal，18770/18780/18781归三个企业微信入口，18761归韩国小说SSH隧道，19443归provider-neutral-tokyo-tunnel。十个unit均active/running；EnvironmentFiles均未配置不等于没有内联环境或认证。generic provider-neutral-tunnel仍not-found；现有客服Wants指向该名称，接续候选必须准确处理，不能把两名称当别名。东京443 PID可见但不属固定10unit，不能写成端口无主。

下一批集中解决上个工具未识别的Python模块启动、SSH L/R/D关系、VPN启动方式和入口源码静态依赖。使用已接收S06归档和R2 verified/code，源码按原服务器1363清单逐文件核验，不能用GitHub同名源码替代；不重新采集、不读数据库/密钥/EnvironmentFiles、不执行应用，不安装或启停服务。动态资源/私有材料闭包仍不可由AST推断为PASS。原19/7项不重跑，新批只测本解析器。


## S07 国内独立安装实际超时（2026-10-17 00:45 Owner回执）

Owner在韩国执行准确ae5e03d9安装器，国内root认证后进入源码落盘及独立环境阶段，最终返回`DOMESTIC_STAGE_HOLD_PRESERVE / DEPENDENCY_STEP_TIMEOUT`，协调端返回`REMOTE_INSTALL_FAILED_OR_UNKNOWN_PRESERVE`。本次是实际私有新目录安装尝试；没有得到依赖安装、安装后源码复核或保护对象前后相等的成功回执，不能认定S07完成。准确终端证据已脱敏保存为`evidence/pr99-service-handoff/s07-domestic-stage/OWNER_INSTALL_TIMEOUT_20261017.json`。

保留国内`/opt/xuanjun-migration-s07`、`/var/lib/xuanjun-pr99-s07-stage-v1`及韩国`/root/pr99-s07-domestic-stage-v1`。原安装器的超时处理会终止自己创建的依赖子进程组，原目录和日志不删除、不重跑原安装器。下一步只读核对具体失败日志分类、已装依赖元数据、源码哈希及当前保护状态，再形成有准确前置条件的依赖续接。下载/网络错误尚未从日志确认，不提前归因。未执行unit安装、服务启动或反代切换；东京继续运行。


## S07超时原因已实机定位，改走韩国下载+国内离线安装

2026-10-17 00:52 Owner-root只读输出：79份源码无摘要差异；venv只有pip/setuptools；依赖日志显示官方PyPI实际下载约10–16 KB/s，到900秒仍在下载idna。准确脱敏诊断见`s07-wheel-continuation/OWNER_DIAGNOSIS_20261017.json`。不是源码校验失败，也没有业务包安装成功。

按#6219362469直接迁移授权形成新续接脚本：保留原目录/日志/源码，在韩国下载相同三个准确版本及wheel依赖，整包和逐wheel摘要验证后国内--no-index --require-hashes离线安装。旧安装器不重跑；旧失败不覆盖；新续接单独目录、失败保留。新增本地9项边界测试通过，不冒充Hosted CI或主机PASS。当前新续接未执行；完成后还需实际运行材料、服务及入口接续。东京继续运行。


## 2026-10-17 S07 Owner offline dependency continuation and next runtime inventory

Owner terminal reports `DOMESTIC_S07_OFFLINE_DEPENDENCY_CONTINUATION_PASS`; PR99 receipt #6220815091 read back. 79 source hashes, 11 wheel distribution versions, third-party imports and pip check PASS; protected state unchanged during continuation. Original timeout preserved; first offline transport attempt UNKNOWN with empty logs and subsequent absent remote directory/process count0. File stdin/exact archive length patch reused original wheels with manifest/tar hashes; actual root cause not proven. Owner launch `/root/pr99-s07-transfer-fix.h8Mz9ued`. Package SHA256 `9b702576d48883786d051b2f1b49972baf94db3d1e8bf330ee59250a5974efa3`, wheel tar SHA256 `b04409509e43e80aff7fb655cc91b76cff2dad04ea01b8087837ebe7ec4c289a`.

Evidence is Owner-root transcript, not direct host login/independent review. Source+dependencies complete; services, runtime configuration/data, reverse proxy and S08-S10 pending. No service actions, application imports, DB reads or production cutover. Tokyo remains running.

Next tool: `evidence/pr99-service-handoff/s07-runtime-inventory/inspect_received_runtime.py`, source commit `442a70918965bb39faf9d0cd54aaaae8db0bfde1`, SHA256 `295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134`. Static inventory of already received private code/three units only; environment variable names, literal path clues and IO/dynamic call sites. No arbitrary environment values/raw unit output, application imports, config/key/database reads, networking, writes or services. Frozen helper/source/archive identities verified. Local synthetic value-redaction, environment/subscript, unit-name, path rejection and compilation checks passed; not Hosted CI or host acceptance. Tool not host executed; static findings cannot prove runtime closure or authorize cutover.


## 2026-10-17 Owner received-runtime static inventory

Owner ran pinned inventory in `/root/pr99-s07-runtime-inventory.8no57zD5`; result `S07_RECEIVED_RUNTIME_STATIC_INVENTORY`. Exact receipt saved in `evidence/pr99-service-handoff/s07-runtime-inventory/OWNER_RUNTIME_INVENTORY_20261017.json`. Three received units use admin:admin and /opt/trading-system, inline environment name PYTHONPATH. Source references include Portal credential-store.env/master key, WeCom state, database connection, referral and knowledge configuration. These are syntax clues, not proven required live-path closures; don't copy entire OpenClaw or create empty data stores. No app import, config/key/database read, network or service action. Owner transcript is not independent host verification.

Next code `resolve_storage_contract.py` commit d25e5a562acea75e793c18a31d8f536fc7f52d35 SHA256 cc27913ca76e1cae58008c8c7c5997bba04ceee7950ff3dacec30bcb9f9a78eb authenticated by GitHub byte readback. Resolves constructor parameters/path expressions for nine relevant existing source files; every non-path literal redacted, including uppercase secret literals. Local constructor/path/redaction/compile checks PASS; Hosted and host execution not run. It only reads frozen helpers and original private source package, not actual business data. Actual runtime data/credential transfer, domestic service identity/units, start and proxy cutover pending; Tokyo continues running.


## 2026-10-17 Storage wiring received; bounded material staging prepared

Owner projection `S07_STORAGE_WIRING_STATIC_PROJECTION` recorded in OWNER_STORAGE_WIRING_20261017.json. Portal default `/opt/trading-system/runtime/secure-secrets-portal/credential-store.env`; channel identities `/opt/trading-system/runtime/v8-domestic-operations/operations-secretref-store`; two WeCom state roots; project database/data/trading.db (default derivation with historical observed source path). Static expressions include redactions and truncations: not complete source review or runtime acceptance.

Prepared `s07-runtime-materials/stage_runtime_materials.py`, source 8f80d0cb60ff68a3bcbbfed6506eda3126cb4761, SHA256 0076b30aec052366ac2f7ec6adfa5ff13b9c54f21fa50221c72d9415ddfc6c7f, byte readback matches. Local7/7 checks: actual temporary SQLite backup/archive, source drift, symlink, hardlink, missing master-key-file binding, traversal/unrelated path rejection, tampered manifest. Hosted CI and host execution NOT RUN.

Under existing Owner direct S07 migration authorization, next Owner-mediated Korean invocation connects fixed Tokyo root identity, validates current79 code hashes and exact3 current unit hashes/admin:admin/cwd/no unreceived overrides, rejects storage CLI overrides, privately collects only4 fixed runtime trees plus2 exact project config/knowledge and2 exact referral candidates, and one preliminary readonly-source SQLite backup/integrity check. Per-file type/hash, 10000-file/256MiB bounds, file-set/current-content and unit/PID pre/post gates; no recursive OpenClaw, arbitrary env export, service action, API, trading, proxy change or domestic install. Private key/data bytes NEVER go to chat/GitHub/CI. Korean `/root/pr99-s07-private-materials-v1` is one-use; failure preserves partial data/logs, no blind retry. Source private staging directory is retained. Live writer is NOT frozen; this is NOT final cutover state or production acceptance. Old R2/S06 permits not reused. Tokyo remains running.


## 2026-10-17 07:38–07:44 Owner S07 staging failure

Owner launch /root/pr99-s07-material-launch.Fwej5Q9b authenticated Tokyo root then held REMOTE_STAGE_FAILED_PRIVATE_LOG_PRESERVED; local materials.tar0 bytes, receipt absent, failure36 bytes, private SSH log224 bytes. Filtered exception RuntimeError SYMLINK_PARENT. No success or source partial-action claim inferred from empty output.

Owner follow-up metadata excludes /opt/trading-system and /etc/systemd/system/three exact unit fragments/parents as symlinks. Project root UID/GID1000:1000 inode1599295 dev64771. Actual failed deeper source/runtime/config path still UNKNOWN. Do not relax link guard or replay old staging.

New metadata-only diagnostic inspect_all_candidate_paths.py commit ceb3942afd8db530540ddc485d7eab7c893a9af3 SHA256 a089bfa39d6fee38f866000e80861d384bb2a2352c66eab569f7c796c7efa054: reuses pinned79-file source inventory and fixed allowed candidates, bounded parent/runtime-tree metadata and private traceback line/function projection. It does not follow link directories recursively, read business/config/key contents, open DB or take service actions. Local synthetic parent/nested links, missing paths, no-content projection and compilation checks PASS; Hosted and host acceptance not run. GitHub byte readback matches. Source staging failure retained; Tokyo continues.


## 2026-10-17 07:46 diagnostic SHA correction

Owner checksum failed before execution/Tokyo connection. Developer had calculated SHA on a local test copy with ONE EXTRA TRAILING NEWLINE. Re-read exact GitHub ceb3942afd8db530540ddc485d7eab7c893a9af3 original:4933 bytes, correct SHA256 `6d68a59982d41dbba710a8735690026a7ba1d9917367e0101c2c97f0dc41755e`. Appending one newline exactly reproduces incorrect prior `a089bfa39d6fee38f866000e80861d384bb2a2352c66eab569f7c796c7efa054`. Code/commit unchanged; previous incorrect digest retained as history. Owner can verify already downloaded /root/pr99-s07-all-paths.aLvfyxbJ/check.py against correct hash before executing. Do not bypass checksum or rerun material staging.


## 2026-10-17 07:47 observed alias and exact v2 continuation

Owner returned293 metadata entries, single link /home/admin/.openclaw/workspace -> /mnt/btrfs-workspace/ws-398ab6 (link dev64771 inode654102 uid/gid1000 mode0777; target dev37 inode259 uid/gid1000 mode0755). Optional /home/openclaw_ops absent. Private traceback remote_pack114/read_file48/need40 binds failure to payload-read loop; exact original source places it before master-key presence check and private source-stage/SQLite creation. Some private files had been read in memory, no successful archive receipt.

V2 commit127e4a942d1cbeadb67b545a47758e1e6827c8dd updates existing stage_runtime_materials.py. Exact GitHub bytes16917 SHA256137a2acea1924b4c62e43abfe6f8689c64450db868c7a216d759a16779c939b4, readback equals tested source. Only the exact referral JSON receives a mapped canonical read; fixed link text/resolve/identity and fixed target identity/permissions checked, canonical parents/leaf still reject other links, and pre/post binding checked. No general resolve/follow override or recursive OpenClaw transfer. New Korean /root/pr99-s07-private-materials-v2; v1 must retain exact failure, absent success receipt, empty tar and matching private error; no delete/rename. New7 boundary checks plus affected original7 actual temporary SQLite/archive checks14/14 PASS. Hosted/new-host execution not run. Prior once licenses not reused. Scope remains private preliminary materials only; no domestic install, API, service/proxy action or final cutover. Tokyo remains running.


## 2026-10-17 07:50 Owner material V2 success; domestic private stage prepared

Owner terminal S07_PRIVATE_MATERIALS_RECEIVED_PRELIMINARY_PASS:165 files/47099890 bytes, file hashes/SQLite integrity/current79 code/current3 units PASS; source private credentials preserved. No API/service action or domestic activation; not final snapshot. Owner launch /root/pr99-s07-material-v2-launch.mgOIzkS1. Selected receipt committed; actual payload/manifest stay private on hosts.

Next transfer_private_materials.py source ebfce46c8c67d1e2443566c0c1b3cd4fbe2cb160, exact GitHub11850 bytes SHA25690b49446307de25820b8190988582a53f05cc093ea97655d567cdf96a275df79; byte readback equals tested source. Korea validates frozen source helper/receipt/private manifest/archive, gzip-compresses same preliminary point, transfers via strict domestic host key and file stdin, receiver reads exact compressed length/checks both hashes and bounded decompression. Domestic validates installed79 code and successful dependency receipt, unpacks regular allowlisted files under NEW /var/lib/xuanjun-pr99-s07-private-materials-v1/received root0700/files0400, verifies all hashes and actual readonly SQLite integrity and protected before/after state. No application imports, service/unit/proxy operation or active runtime replacement. Original source/current/venv untouched. Local7/7 pass:47MB-class synthetic165-file staging+real SQLite, gzip length/hash, expansion bound, traversal, duplicate, manifest tamper, existing-directory preserve. Hosted/host execution not run. New attempt roots preserve failures and prohibit blind retry. Owner enters domestic root password only in terminal. No new Tokyo capture or old stage replay; final data/activation cutover still pending.


## 2026-10-17 07:54 domestic material success and temporary copied-root startup prepared

Owner DOMESTIC_S07_PRIVATE_MATERIALS_STAGED_PASS165 files47099890 bytes (wire1868986), hashes/SQLite/current79code PASS; protected state unchanged; no active runtime replacement/app import/production service action. Tar SHA256dee6e24933f6a9b14c12ea0b838099093c40e53dda447360080d382793bc8c8c; wire SHA2567b0c1dbde63482c10d02ff51081fd1cdee0d3f1c17b1fbd75ffe3b111e40ab4f. Owner receipt saved; not independent host login.

Next isolated_start.py commitd7b7a35abe2b4e112745d5931f10bdc2d865c219, exact GitHub19157 bytes SHA256546cadada3c8ec51a2576387d08718b43f6bd1485368676e194436401a701b78, readback equals tested source. Local8checks PASS: exact script/module, host/port-only command admission, shell/entry/worker/storage/external-port/duplicate-option refusal, actual temporary separated copy/referral path, traversal/collision and pinned-helper rejection. Chown mocked in local copy test; namespaces/chroot/UID/network/process runtime NOT host tested; Hosted not run.

Owner-mediated next run authenticates domestic, validates existing archive/material/current79source, then copies all inputs and venv into a NEW rootfs under /var/lib/xuanjun-pr99-s07-isolated-start-v1. It uses absolute unshare/mount tools, new mount+network+PID namespaces, requires ONLY loopback, makes fixed system binary/library binds readonly INSIDE namespace, launches exact three Python entries in copied chroot as UID/GID65534 with no_new_privs and file/CPU/memory/FD bounds. No host runtime or canonical ledger mount. Process/listener/healthz HTTP statuses recorded separately; 404/unknown is not application/auth/full runtime acceptance. Applications are stopped and PID namespace exits after observation; bounded namespace timeout kills it. Logs stay root-private; copied DB/state can change only in scratch replica. Original materials/source/venv and protected website/services preserved. No persistent unit/proxy/public callback/production cutover, no final snapshot. Root/PID/network/cap behavior requires actual host evidence; don't call local tests host PASS.


### 2026-10-17 08:06 CST — S07 portal command admission correction

Owner's pinned read-only projection confirmed the portal's extra positional argument is the source-declared `serve` subcommand; portal source SHA256 `57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1`. The original `UNSUPPORTED_START_OPTION` occurred on Korea before domestic authentication or attempt creation. No remote isolated run was performed by that invocation.

Fixed script commit `ef49895f1ad8a159171ad61f9da2059d3e6fde0c`, SHA256 `d0e8f5ee494dd3e71705e9b5dba86c90f94f0d8262601a72fde5837c204f817d`. Only the exact portal entry may accept one leading `serve`; other options/subcommands remain rejected. Test commit `f5d54f0e1e7818e9142ed1aa61dc6ac89e2ea6e8`: 10 local checks passed, including observed command, remote reconstruction, and rejection scope. This is local evidence, not hosted CI or host isolation acceptance. Owner execution of corrected isolated startup remains pending. Production cutover and Tokyo retirement remain HOLD.


### 2026-10-17 08:13 CST — S07 isolated root traversal correction

Owner v1 domestic log: namespace preflight succeeded, portal exec raised PermissionError errno13 at child Popen; no contact/customer-service log, no receipt, failure preserved. Bounded /proc projection found zero related processes. Read-only post-namespace path projection: /venv and /venv/bin 0755; python -> python3 -> /usr/bin/python3; unmounted /usr 0700. This does not show active namespace bind mode. Source confirms private umask077 masks rootfs mkdir0755 to0700, blocking UID65534 traversal. Explicit rootfs, skeleton and /dev chmod0755 added; private coordinator stays0700 and copied business data remains restricted.

New v2 local/domestic attempt paths preserve v1. Domestic preflight requires v1 failure.json exact status, absent receipt, protected snapshot unchanged and no related process before proceeding. Corrected script commit `93616b2e47a1bfb6b59d7107de03df59ed81cbb6`, SHA256 `b82253930bf134fa3354c5fd2c33aa860113a828b54b7717f3599dd1d50f22f2`. Local tests: 13 run, 12 passed, 1 skipped because execution environment prohibits chroot/uid transition. No hosted CI or domestic acceptance claimed. Owner v2 isolated execution pending; no production cutover or Tokyo retirement.


### 2026-10-17 08:21 CST — batch lazy-source continuation

Owner Korea /root/pr99-s07-closure-check.Ay4vkCOC: existing R2 index1360 Python modules, original79 matched; conservative candidates125 (+46), including audit_repository SHA256 f777007abda3df14d07f76abea0339788936e7cb0544cc8c180df146d071bfa6. Three dynamic import sites reported; completeness not proven. No imports/transfers/services performed by inventory.

Combined continuation script `evidence/pr99-service-handoff/s07-source-closure/batch_isolated_start.py`, commit `bc0f6627d5593e7b3035d26e1c792c24c97bdcfc`, SHA256 `4185dd98491d16d3c7f8c76eae9bcc9aeb515f0a5cbfbfa2a58f313224e5cda2`: pins all46 Owner-reported hashes, excludes only empty signal/__init__.py to avoid shadowing Python standard signal (rejects explicit signal submodule requirements), transfers remaining45 over pinned domestic SSH, verifies exact supplemental members and hashes on both hosts, constructs new v3 copied root with124 source files, inherits no-external-network/PID/mount/chroot/UID65534/timeouts, starts/stops three apps, returns sanitized errors inline. No update to installed app79 or production units. Includes data/repository source modules only; does not launch trading/Finance tasks. Existing v2 receipt must show all3 exit1, no listeners, stopped, protected snapshot equal before/after/current, matching shared missing-module errors and no related processes. v1/v2 preserved.

Local19 tests:18 passed,1 skipped (runtime prohibits chroot/UID transition); hosted CI not claimed. New45 provenance is frozen existing Korea R2, not current Tokyo byte recheck; must resolve current-source consistency before production. Owner combined execution pending. No runtime PASS, production cutover or Tokyo retirement claimed.


### 2026-10-17 08:58 CST — authentic bridge material continuation

Owner source-only AST projection confirms both failed clients use internal-bridge under /opt/trading-system/runtime/v8-domestic-operations and require domestic_bridge_cert.sha256. v3 contact health200; portal/customer_service errno2 on exact pin file. Three app processes stopped and protected snapshot unchanged. Prior v3 execution is partial, not runtime PASS.

Prepared bridge continuation script commit `2363eed13fb99df6f9f80701a8c52eae5243bc21`, SHA256 `9cfbdae945c7cf0e9c36866d8a9de8e3f8b42ec30994fd162c5764994da5ea98`. Batches: static AST-only path-default interpretation for two bridge clients; pinned Tokyo SSH read of at most8 exact top-level files, <=64KiB each, with unchanged regular-file/no-symlink checks; current Tokyo124 Python source hash recheck against initial79 plus pinned45; private Korea receipt; pinned domestic transfer and per-file/member/hash validation; new v4 chroot isolation with inline error projection. Certificate pin must be real64hex; no placeholder or disabled verification. No directory recursion, public credential output, persistent unit/bridge/proxy mutation, or production callback calls. Both secrets and certificate materials remain private on hosts. Existing v1/v2/v3 attempts preserved; v3 exact partial receipt, error logs, stopped processes and before/after/current protected state required before v4.

Local24 checks:23 passed,1 skipped because runtime prohibits chroot/uid transition. No hosted CI or v4 host acceptance claimed. Owner execution pending (Tokyo password then domestic password in terminal). Production cutover/Tokyo retirement remain HOLD.
