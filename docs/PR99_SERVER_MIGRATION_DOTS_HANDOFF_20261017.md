# PR99服务器迁移完整交接：原Work执行窗口 → dots

日期：2026-10-17，北京时间。Owner于13:27明确要求交给dots完成。本文为迁移执行交接，不是生产放行。原窗口只完成本次归档、停止登记与回读，之后不继续迁移开发、云命令或安装。

## 1. 执行权和停止回执

- 原执行方：本会话“四机RAM/SWAS迁移执行窗口”。
- 接任：dots（玄钧AI-云汇），Owner已授权接手服务器迁移。dots应先核对本文及最新HEAD，在原PR99确认接手后成为本迁移范围唯一writer，不另建任务/分支/队列。
- 原窗口停止新增迁移写入；无已知在途或结果未知的本窗口SWAS调用。最后受保护入口run39005472107/job117316933627已终态failure/HOLD，**在任何STS/SWAS调用前停止**，云调用0、主机命令0。
- 最新真正主机操作为r2复制品验收run39004155870，已成功结束且临时应用进程/监听全部清理。
- 本地交接检查：相关后台进程0；最新交接前HEAD对应已列工作流均completed。此结论不证明其他窗口没有任务；没有为了交接再发Root命令刷新远端/proc。
- 没有本窗口常驻后台迁移writer。没有安装任意Root RPC服务。
- 私有目录、失败批、日志、源码、备份和本地临时镜像全部保留，未清理/重置。不声称“完整git checkout干净”。

STOP_RECEIPT=STOPPED_FOR_DOTS_HANDOFF
MIGRATION_WRITER=DOTS_PENDING_ACK
INFLIGHT_OWN_SWAS=NONE_KNOWN
REMOTE_RESULT_UNKNOWN=NONE_KNOWN
PRODUCTION_MIGRATION=NOT_COMPLETED
PRODUCTION_CUTOVER=NOT_EXECUTED

## 2. 原任务和准确断点

仓库：https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control
PR99：https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/99
原分支：build/tokyo-korea-migration-prep-20261014
交接前实读HEAD：373419cdfa635005764020beed86e31e123e1c2d。
本文和停止登记会产生后续提交，接任以GitHub最新HEAD为准，不能回退覆盖。

必须先读：
1. plans/PR99_PHASE_C_STATE_20261016.json
2. plans/PR99_SERVICE_HANDOFF_EXECUTION_LEDGER_20261016.md
3. plans/PR99_MIGRATION_PROGRESS.md
4. 本文及PR99最新有效评论。

原权限：Owner长期直接迁移授权已存在，不重复索要密码、AccessKey、SSH命令复制或笼统再次授权。独立准确准入、唯一writer、最终数据和生产切换条件不是已自动完成的事实。原Owner指令PR99#6219362469；停止安装审核请求#6229861598。后者只覆盖当时停止安装候选，**没有审核决定，也没有覆盖后来新增的全部启动代码**。

## 3. 当前真实成果和未完成状态

已做了恢复、副本落盘、离线依赖和隔离运行准备；**三应用尚未生产安装/启动，入口未切换，东京未退役**。测试HTTP200、无效请求403、CI成功不能叫生产迁移完成。

### 最近三批实际主机执行（均成功且已结束）

| 批次 | Run / Job | 国内InvokeId | 结果 |
|---|---|---|---|
| r2源码 | 39004046272 /117312742713 | t-sh070a4jun5nfnk | 124份源码，新版本domestic-r2；122份继承r1字节，两份仅改桥接端口 |
| r2运行副本 |39004107195 /117312919573|t-sh070a4mwpu2oe8|2906普通文件/114962378字节/4链接；逐文件哈希通过 |
| r2回调与重启 |39004155870 /117313065796|t-sh070a4pjzs5dkw|两轮×三健康200；每轮两个无效鉴权请求403；临时进程/监听全清理、protected未变 |

[源码run](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39004046272)
[运行副本run](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39004107195)
[验收run](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39004155870)

准确实机结束时间2026-10-17 12:52:15 CST。
完整公开脱敏回执：
evidence/pr99-service-handoff/s09-install-candidate/R2_EXECUTION_RECEIPT_20261017.json。

r2数据仍来自原165文件初步副本，**不是最终快照或canonical writer**。两轮测试在复制chroot、私有网络namespace（只有lo）、UID/GID65534运行；真实生产专用身份、上游签名成功和业务链路未验。

### 实际修复原因

原东京两个客户端源码固定连接127.0.0.1:19443（东京SSH隧道），国内桥接实际监听18443。新r2仅改两个构造调用19443→18443，没有改现有桥接或东京隧道：
- ai_service/telegram_customer_service_canary.py：
  原83904b6994db02b2702563eaaace50399caaf968864bd7f0ea355b4350462150
  新07e5b1ba8536ece13ebcd024d448fd99eb93159f7f3217d16b042f95434c2d6b
- ai_service/wecom_customer_service.py：
  原aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402
  新701c5026b08ef13e38d30cc8b6da26649968262e733f3631cae9d60d59f87c6e

此前无效鉴权探针发到/导致404；已纠正为：
/wecom/customer-contact/callback
/wecom/customer-service/callback
实际无效签名均403；不代表真实签名成功、上游HMAC或企业微信生产回调已通过。

## 4. 已保存源码、测试、成熟度

以下路径均在 evidence/pr99-service-handoff/s09-install-candidate/：

| 文件 | 精确身份 /状态 |
|---|---|
| stage_bridge_release.py | SHA bb54946c5b2b068180af79bca0efca51ec68c132a05bd01acfb2fa21ea108da2；实际执行源码提交abd844683327d35b34b497af71023e8accc174b0 |
| stage_r2_runtime.py | SHA5b3d73850c588bdb0cc95ee5616b351603350dc572dd9959960e06c23119e4b7；实际提交4a25631b95bca43f61cdd76c5eee36497ad6a69b |
| accept_r2_callbacks.py | SHA55d1e59a1fa271eb134427cf3b4c4f1372316baba7e69d9b27a1ab0edef0af68；实际提交7f430ffc02be07a916f84ccb2fb5614c385defc4 |
| stopped_transaction.py | SHA99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315；仅禁网候选停止安装和自有停态unit回滚，未主机执行 |
| test_stopped_transaction.py | 9项临时文件系统/模拟systemctl测试 |
| production_start.py | SHA6ad51228f60690365ee4004c8c05b9c982eb2de70551ac8061142fcb4c93fa32；新增启动源码候选，**未实机、未独审、不可直接部署** |
| test_production_start.py | 4项源码/模拟启动失败围堵检查；不代表完整安装异常路径已覆盖 |
| transport_contract.py | 精确脱敏AST投影；run39003973982/job117312529855，Invoke t-sh070a4g47hdm2o，确认两个19443构造调用 |
| build_candidate.py /PLAN.json | 早期模板制品，REVIEW_CANDIDATE_NOT_INSTALLABLE；不能用它直接上线 |
| STOPPED_TRANSACTION_REVIEW.md | 当时停止安装范围的包说明；不是后来完整生产启动批准 |

新启动候选设计为固定domestic-final-v1/rootfs，要求：
- 固定国内主机和Root；
- 由原独立权威提供准确Root私有admission；
- 专用xuanjun-s07身份已经准备；
- 真实final-checkpoint、source-writer-fence、canonical-writer-assignment文件及其批准哈希；
- 准确文件/链接集合及unit哈希；
- 新unit不存在、端口未占、启动前重新验输入；
- 启动/监督三应用与健康检查，失败仅停准确自有服务、保留数据，不复活旧writer，不切Nginx/current。

**这些要求只是源码门禁，不表示真实输入存在。** 候选尚未完成完整生产触发接线、真实身份/权限准备、最终快照生成和接收、全部崩溃恢复/持久日志与真实鉴权验收；不能把4项模拟测试包装为完整生产安装事务。需要dots继续检查受影响完整调用链、补齐异常恢复和真实输入，集中验收，不能直接签发自己的私有许可。

准确新增代码CI：
checkout23b9b42bbfa7655bb38c0c1ebc83f4edadc3efca，
run39005621738/job117317379867 SUCCESS，
2026-10-17 13:16:01 CST：9项停止事务+4项新启动检查通过。
均为临时文件/模拟systemctl范围，不是PID1/systemd239或生产主机通过。
[CI](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39005621738)

## 5. 已实证的工具入口、凭据和限制

四机均通过原Actions Secrets → STS AssumeRole → SWAS RunCommand →查询root结果。是**SWAS轻量服务器，不是ECS实例ID**。

| 主机 | 地域 | 实例 | Role |
|---|---|---|---|
| 英国 |eu-west-1|40dfc6a47d5e4363b9da7d0d6ab01cb1|acs:ram::1107191612880779:role/xuanjun-ai-esc|
| 韩国 |ap-northeast-2|09207081a09a466aa0079b07b5e3e7ca|acs:ram::1691189778575891:role/xuanjun-automation|
| 国内 |cn-shanghai|3a22c458934142eea89ec6e3bf481a57|acs:ram::1384884686754410:role/xuanjun-automation|
| 东京 |ap-northeast-1|68985c531add4e90a131aef703a389e6|同国内|

国内hostname iZvt5t8tlrm8oiZ，IP47.101.152.210；
东京iZ6wee8q9z4t03hvqumwfhZ，47.245.53.152；
韩国iZmj7a5kwr75qc1tul4kf9Z，43.108.99.66；
英国iZd7oeikknn1z21sq6ji6zZ，8.208.119.115。
英国/韩国默认python3=3.6.8；韩国已有显式/usr/bin/python3.11；国内/东京3.11.6。

原Repository Secrets只有名称：
ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET。
由Owner/原仓库凭据维护主体保管，运行时注入；不索取、读取、导出密钥值。不需要Owner重新做四机RAM授权。
四机身份成功run38991455661/job117275780078（attempt2）。
完整原通道文档docs/ALIYUN_FOUR_HOST_EXECUTION_HANDOFF_20261017.md为历史能力记录，09:54断点不是最新迁移状态。

### 当前原生工具能力的准确修正

本窗口有GitHub文件/评论/标签/CI日志工具，没有workflow_dispatch工具、可用gh CLI或本地GH_TOKEN/GITHUB_TOKEN。
但已经实现并真实触发：
.github/workflows/pr99-controlled-stopped-install.yml
提交d7dcfd0bf82a93b2416a660fd0cf1b53766d804a。
仅pull_request labeled，不由push触发Root。
Owner actor_id332398908、原PR99/固定分支、标签pr99-s09-stopped-加事件HEAD前12位绑定；
只有国内host；原Root私有准确admission仍必须存在。

实际用GitHub add_issue_labels触发标签pr99-s09-stopped-d7dcfd0bf82a：
run39005472107/job117316933627于13:13:35 CST终态failure：
INDEPENDENT_HOST_ADMISSION_NOT_ISSUED_NO_CLOUD_CALL。
**云调用0、主机命令0**。说明标签触发能力已验证；不是RAM失败，也不是主机安装失败。
[入口回执](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39005472107)

禁止把canonical JSON的independent_host_admission手改true以“让测试过”；这个标志不能代替真实独立Root准入。此入口仅接停止安装脚本，**没有接生产启动/切站动作**。原stopped admission预期/etc/xuanjun-pr99/s09-stopped-install.admission.json；生产候选另需s09-production-start.admission.json。均未由本窗口签发或部署；不凭文档声称现场存在或不存在。

已触发标签是历史消费记录，不移除再添加重放。未来新动作必须完成准确绑定、真实授权和持久消费/未知查询，不能普通代码push偷跑Root。

## 6. 主机目录与禁止重放

国内：
- /opt/xuanjun-migration-s07/app：原79源码安装副本；
- /opt/xuanjun-migration-s07/venv：已离线依赖安装；
- /opt/xuanjun-migration-s07/releases/domestic-r1：124源码和旧运行副本，历史验收保留；
- /opt/xuanjun-migration-s07/releases/domestic-r2：本轮真实新代码/运行副本；
- r1、r2隔离测试后rootfs的opt/home权限曾为UID65534测试调整；不要当生产安全权限已准备。usr/lib/lib64等测试bind仅私有namespace内临时挂载，不能当持久系统库绑定已完成。
- /var/lib/xuanjun-pr99-s07-private-materials-v1/received：165份初步私有材料；
- /var/lib/xuanjun-pr99-s07-isolated-start-v1/v2/v3/v4：旧成功/失败/未知现场一律保留；
- r2/callback-restart-acceptance-v1：最新隔离批私有日志/receipt；
- domestic-final-v1和新生产STATE未由本窗口创建/启动；未再Root刷新现场，不把“我未创建”说成“现场必然不存在”。

韩国：
/root/pr99-current-point-received-v2/verified/code/：原R2；
/root/pr99-s07-domestic-stage-v1/package.json：79源码包；
SHA9b702576d48883786d051b2f1b49972baf94db3d1e8bf330ee59250a5974efa3。
/root/pr99-s07-private-materials-v2/materials.tar：47099890字节165份初步材料。
/root/pr99-s07-swas-transport-v1及peer/root/pr99-s07-swas-input-v1：成功消费，禁止重放。
东京现网/opt/trading-system：admin:admin，不覆盖或停共享项目。

重要历史：
- v4 run38992581089/job117277978082，Korea Invoke t-kor709ol1r4xvy8；三健康200、临时停、保护不变、当时东京124源码PASS、两个真实桥接材料私有传输，禁止重放。
- r1 code run39001447378、runtime39002237032、restart39003075282：继承已过未变证据。
- 旧r1自动重复run39003103198/job117309973655，Invoke t-sh070a371eaocn4失败；
  query-only run39003189371确认FileExistsError，重复启动前拒绝，旧现场保留，不能当成未知在途。
- r2三个新批也已消费，不能为取得新回执重跑。
- 真实桥接pin/HMAC私有文件不进GitHub/CI日志/制品；不造pin、不禁用现有pin认证来通过测试。

## 7. 剩余6个大节点及dots应完成的工作

| 节点 | 真实剩余 |
|---|---|
| 1 运行配置/依赖 | 专用生产身份、完整有效环境、只读系统库绑定和最小写入目录/权限；真实bridge TLS pin/HMAC/上游链路验收。端口两处已改，不能重复修。 |
| 2 生产安装/启动/回滚 | 完成准确完整事务、生产触发接线、持久调用/消费/超时/未知/部分执行恢复；本轮源码候选未独审/未实机，不可直接上线。 |
| 3 真实验收 | 原隔离200/403继承；仍缺真实签名成功、真实上游、生产监督重启和恢复验收。 |
| 4 最终数据/唯一writer | 明确各数据真实writer/共享依赖，准确原writer停止/隔离、一次一致性最终快照、传输核验、目标唯一writer和对账。不能用初步165副本。 |
| 5 入口切换 | 准确域名/反代/端口/旧current和配置快照，验证新服务后一次受控切换及实机HTTPS/回滚，不覆盖现网站。 |
| 6 东京退役 | 所有保留职责迁出或Owner明确取消后再验收；不得因三应用测试过就关机。 |

不是“再跑一次CI就完成”。仍有代码和真实输入工作，不应把全部缺口归因Owner没授权或独审没动作。

建议接手顺序：
1. 在原PR99确认接手并核对最新HEAD/在途结果，避免第二writer。
2. 复用本轮r2和既有审核，核对新增startup/entry真实缺口，形成同一完整执行方案，不再逐点送审。
3. 以最少必要现场查询补齐真实身份、共享数据writer、最终输入与入口现状；不重复恢复点导出/旧失败探针。
4. 完成完整启动/最终快照/安装/失败恢复/入口回滚接线和整批测试，再集中原第5项审核及准确一次执行记录。
5. 实际执行到可确认终态，记录run/job/InvokeId/版本/主机/回执；未知先查询，禁止重发。
6. 完成真实业务/HTTPS/数据对账验收后，再处理东京剩余依赖；不将源码通过当迁移完成。

## 8. 保护对象及跨任务边界

- PR99的124源码/2906运行文件是portal/contact/customer_service迁移副本，**不是PR122网站/客户中心完整发布包**。
- PR122网站已有旧版国内生产发布记录；最新登录/展示增量未生产安装。PR122网站writer已是dots；本交接迁移职责不扩大任何尚未验收的支付/客户资料/网站权限。
- PR122直接迁移指令#6229967279要求一次完整新调用链验收、真实运行条件和回滚；不是无条件启动任意部分代码。
- PR122#6230117672仅7路径网站交互源码/制品限定通过，不是PR99生产安装许可。
- 保留国内网站/var/www/wenwenwenyiyiyi.work/current及其现用Nginx片段、国内bridge18443、winctl18444、韩国443 MoreLogin。
- 原PR58英国P2已封存；不得开第二P2writer或解除旧4服务mask。英国模型替代仍由其原权属处理，本窗口没有英国在途调用；最后已知英国只读run38992820588/job117278706310/Invoke t-gbr709owjajkg74已成功结束，不为交接重跑。
- 东京20443仍支撑国内/韩国反向19444；东京SSH -L19443→国内18443保留。四Finance timer、VPN/tailscale exit、3个Cloudflare容器职责需确认接续/取消，不能随本应用迁移删除。
- 不动币安交易Writer、订单/真实资金、Novel、Yibi等未批准对象。无需购机/删机/扩大RAM权限来绕过部署软件缺口。

## 9. 事件和通知

原“服务器迁移进度通知”只读，不是后台部署执行器。
已取消commit更新触发以免自身提交不断插入只读任务；保留原PR99评论/审核事件及持续webhook，不因交接停用。
新PR评论可能唤醒通知，但不是dots自动接手的证据。dots需要实际读取并确认本文。
不要用新自动通知/marker循环替代迁移writer。
Owner要求减少反复汇报和授权；按真实节点通知，准确说明是否在运行、失败/未知、剩余和链接，不能声称后台持续施工。

## 10. 本地非权威镜像

本窗口临时镜像/tmp/pr99-install-candidate、/tmp/xuanjun-aliyun-check、/tmp/pr99-bridge保留但可能不随新会话可见。
代码均已按上列路径提交原GitHub分支，**以GitHub字节与服务器私有回执为准**；不要要求Owner复制本地镜像或上传秘密。
旧临时文件不构成真实信任、审核许可或生产配置。

交接归档后，本窗口只允许回读/补齐交接引用，不继续源码、标签触发、Root或网站部署。dots接手前不虚构新writer已运行。
