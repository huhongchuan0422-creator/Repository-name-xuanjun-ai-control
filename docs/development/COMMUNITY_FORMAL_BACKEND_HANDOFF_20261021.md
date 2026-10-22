# 社区预览正式后端接线与现场依赖

## Owner范围纠正（2026-10-21，优先于本文历史接线候选）

社区是客户自己的平台；PR122登录是本方SaaS客户登录，二者用户、身份及权限不得默认等同。社区未选配客服对话，不接入国内客服/公共大脑/CRM，不引入AI费用。本文件中把PR122服务授权或国内客户映射列为社区登录、预览前置的历史候选停止推进；已有源码/测试保留为未启用准备，不删除、不挂到原登录或业务路由。

原社区身份路径现状：MiniGateway.login以微信code经WechatCodeClient兑换，CenterIdentity查原WECHAT_MINI绑定、账户状态后发会话，每次业务请求再核scene/project/原Principal与门店范围。上述是源码机制，不能证明现场平台身份已经配置。当前绑定实现依赖同进程Center.session/已验证account和project；复用代码类不代表可复用本方SaaS账号数据。不得要求客户平台用户先注册本方SaaS，也不得删除SHA/type或验证门禁来绕过此实际接线问题。必须核原平台既有注册/身份绑定入口、持久对象和账号归属，再沿原IdentityPort/门店权限薄接；目前尚无这部分现场身份来源证据，不能用fixture建号冒充。

纠偏后的最小验收路径：
1. 固定community-preview域名的当前已证故障为英国/国内本地解析EAI_NONAME，TLS/HTTP尚未进入；下一动作只读核现有权威DNS记录及入口归属，不能断言权威NXDOMAIN或擅改DNS。
2. 英国社区容器尚缺正式bootstrap、既有业务持久数据/平台身份对象与scene→店配置的同版本运行证据。现有from_existing_runtime为组合API，fixture server不可部署冒充真实环境。B5/P2预算未核，社区/视频比例只是上限，未设置额度。
3. 在原平台身份来源明确后，真实wx.login code→原code2session→原平台账号绑定/会话→原门店业务；未知或未绑定身份拒绝，不能自动合并/建号。AppID/既有AppSecret引用、request合法域名、真实code2session与真机资料/门店/订单均需独立实证，不输出秘密。
4. 仅后端READY且原身份接通后才沿既有官方上传通道生成新码；扫码页面非空、真实身份和门店隔离逐项验收。上传成功、合成测试、健康通过均不等于真机通过。payments=false及Finance UNCONFIRMED保持，真实支付资格/资金验收另列。

不需要PR122远端授权、SaaS→国内CRM映射或客服咨询才能恢复社区预览。无新增IAM、真实映射写入、部署、服务启停或DNS/凭据变更授权。历史接口证据留存只供将来明确选配复用，不能继续作为本轮强制缺项。


本文件是原Issue76的源码接线与待确认候选，不证明现场已安装。Owner部署归属沿原Issue76 #6162297518、#6230418580及#6313250273：社区分账与公益视频均在英国既有主机的独立容器；国内Runner只承担既有上传/检查。此前本文件的国内应用服务/systemd候选方向作废，不作为现场操作依据。现有`deploy/community-preview/server.py`使用fixture、Mock兑换和临时数据，不能作为真实客户后端发布。

## 已有正式入口与配置

`MiniApplication.from_existing_runtime(center, runtime, principals, config, app_secret)`复用宿主已打开的Center与原StageRuntime，不创建Center、数据库、账户、密钥、权限或listener；关闭应用不关闭宿主数据库。凭据由既有宿主受保护入口传入，配置schema不接受Secret字段。实际微信兑换仍使用原WechatCodeClient；不能注入fixture作为真实验收。

`config`必须恰好包含以下字段；真实现场值均待管理方提供原始回执，不能用新建空库补缺。

| 字段 | 合同 |
|---|---|
| version | 整数1 |
| appid | 原小程序AppID；现有源码为wx1d5f8873eaea5392，需核现有账号绑定 |
| https_origin | 受保护HTTPS origin；本任务候选为https://community-preview.wenwenwenyiyiyi.work |
| scenes | 非空scene→{project, principal}；principal是宿主既有对象名，不是客户端自报角色 |
| stores | center/orders/merchants/ads/refunds/quotes/saas_orders/modules的实际绝对文件路径；与已打开连接的main路径一致，文件和直接父目录属当前服务用户且无其他用户权限，不允许内存库或符号链接 |

scene必须指向现有CUSTOMER Principal及当前有效、同租户原项目。原Center负责微信身份绑定和会话，原运行时负责订单与数据。新入口不导入CRM、不自动授予任何账户访问权。

宿主调用顺序：取得原持久对象与受保护配置→from_existing_runtime→原configure_onboarding/configure_operations/configure_commerce→原configure_wechat_applyment→仅对已获JSAPI准入的门店调用configure_payments_from_applyments→按已核Nginx身份与受保护origin调用listen_proxy。存在其他已启用模块时继续调用其原configure方法，不复制系统；缺原对象或现场配置即停止，不能用fixture补齐。当前仅为可调用组合API，不是已部署的现场服务启动器。

支付admissions是已知scene的非空子集，未选门店没有支付配置；同店多scene继续幂等。可信FINISHED查询须经过原RSA验签与原持久记录，再投影sub_mchid；受保护JSAPI/分账产品资格独立校验。状态查询当前是审核员主动wechat_query，自动轮询尚未实现。

## 入口、英国容器与原Center接入

| 层次 | 固定目标/已具备 | 证据缺项与边界 |
|---|---|---|
| 小程序入口 | https://community-preview.wenwenwenyiyiyi.work，pages/home/index?scene=shop1；payments=false | 当前仍BACKEND_NOT_READY；DNS、TLS终结点、入口反代所在主机及实际upstream映射UNKNOWN。国内Runner位置不证明入口或应用部署位置 |
| 社区应用 | 英国既有主机iZd7oeikknn1z21sq6ji6zZ；规划项目域uk-community-payment | 容器名/不可变image digest、非root UID/GID、容器内启动入口、网络/端口/卷及当前存在状态待原始回执；不能沿用原国内systemd候选，也不能挪用P2/B5容器 |
| 正式源码接点 | MiniApplication.from_existing_runtime → 原configure方法 → listen_proxy | 是同进程Python组合API，不是已冻结的容器启动命令。宿主bootstrap、受保护配置引用、实际健康端点路由及同版本运行回执尚缺 |
| 原Center | 精确原Center对象、原StageRuntime与已有持久库 | 原实例实际位置/归属及8类store历史路径UNKNOWN。该API不支持把远端HTTP服务伪装为Center；公共大脑、客服中心固定留国内；源码Center与国内实际服务对应关系NOT_VERIFIED，仅沿既有受控接口明确服务边界，不迁库，不跨主机挂载活动SQLite、不新建空Center或第二身份系统 |
| 持久数据 | 每项目独立卷/数据库角色/备份；config.stores校验容器命名空间内准确路径 | 缺host→container映射、原数据来源/非空历史、schema/版本、单Writer/锁、服务UID和恢复演练证据；不得让两个应用Writer同时打开同一活动数据库 |
| 公益视频 | 同一英国物理主机上的另一独立项目域uk-public-benefit-video | 仅记录部署资源/隔离候选；本窗口不开发视频业务、不另开Writer，不假定其容器或资源已部署 |
| 国内Runner | 原miniprogram-ci上传及既有检查 | 不承担社区或视频应用后端；不把上传成功作为英国服务可用或客户验收证据 |

## 容量证据与资源上限候选

证据范围：
- 原Issue76 #6162297518只确定英国多容器归属，明确UK_CAPACITY_AND_SECURITY_VERIFIED=NO；#6230418580再次保留英国归属，未提供可分配资源数值。
- PR133 #6281322867的RESOURCE_LIMITS仍为UNKNOWN，要求原管理方读回CPU/memory/pids原限额；其中1002:1002是P2历史sandbox profile，不能直接给新业务复用。
- 最近已读PR17 #6313179688的AS768MiB、CPU180s、wall240/270s等是B5单次材料取件工具的进程限额，不是英国可用容量，也不是B5服务预留。不能据此分配社区或视频资源。
- V27 §21.1的4C16G是参考规格，不能作为当前CPU/内存余量证据。现有资料缺带时间戳的当前占用及B5保留预算，本轮不执行英国探测。

因此不填写猜测的CPU/内存/PID/磁盘/日志数值，不生成可执行的无上限容器配置。以下为必须冻结的独立硬上限合同；数值缺项时两项目部署准入HOLD，不将null、0或-1写成容器限额（部分运行时可能将其解释为无限制）。

| 项目 | CPU硬上限 | 内存硬上限/Swap策略 | PID硬上限 | 持久磁盘与临时空间 | 日志上限 | 本轮准入 |
|---|---|---|---|---|---|---|
| uk-community-payment | ≤英国CPU总资源1/5，实际quota待容量回执，且受剩余预算约束 | ≤英国内存总资源1/5，实际hard limit待核；Swap策略须实证 | 待定；独立pids limit | 可分配业务存储≤英国对应总资源1/5；业务卷/DB/WAL/备份/上传/tmp分别冻结 | 单文件大小×保留数及总量均须有界 | HOLD，未设置 |
| uk-public-benefit-video | ≤英国CPU总资源1/3；API/worker合计，实际quota待核 | ≤英国内存总资源1/3；API/worker/队列/DB合计，实际hard limit待核 | 待定；按实际组件合计受项目上限约束 | 可分配业务存储≤英国对应总资源1/3；原件/产物/tmp/队列/DB/备份分项 | 每组件轮转及项目总量上限 | HOLD，未设置 |

冻结方法：对CPU、内存、PID、磁盘分别取得宿主可分配总预算H、已有非本项目且不含B与R的占用/硬预留E、原管理方批准且不可削减的B5/P2预算B、系统运行与故障恢复预留R，定义可分配新增预算A=H-E-B-R。社区C与视频V必须均为有限正硬上限，且C+V≤A；不得把当前低使用率当作可侵占B5的预算。每项以业务有界负载测得的峰值与Owner批准的余量选值，按Owner #6313455771，CPU、内存、可分配业务存储还须分别满足C≤H/5、V≤H/3，C+V≤min(8H/15,A)。比例是上限而非预留或已设置值；PID与日志仍按实际容量冻结有限值，不从CPU比例推算。若预算或硬限额不能由现有cgroup/文件系统证明可强制执行，则不启动该负载。

必须由既有现场管理方一次回交的容量字段：采集时间/hostname、在线CPU与既有限额、CPU峰值/压制信息、MemTotal/MemAvailable/Swap与容器内存峰值、当前容器及B5/P2实际硬配额和Owner保留预算、pids.current/pids.max或v1对应值、目标卷可用空间/inode/现存配额机制、DB/WAL/备份与视频临时峰值、日志驱动及轮转能力、实际cgroup版本和CPU/memory/pids控制器可用性。最新占用缺失时不得宣称可承载。仅列核查合同，本轮不执行命令。

## 隔离与既有凭据引用合同

两项目使用独立非root运行身份、bridge网络/受限出站、卷/数据库/备份/日志/队列和已有SecretRef。项目之间及对B5/P2默认拒绝互访，不使用host network、特权容器、Docker socket或控制面数据/令牌挂载；非必要宿主路径不挂载。具体现有UID/GID、网络名/路由、存储路径、数据库角色和SecretRef均待权威配置引用，不能在本轮新增账号、密钥、角色或权限。社区微信AppSecret/商户凭据不提供给视频；视频发布/对象存储凭据不提供给社区。

## 一次性现场依赖与确认范围

以下动作均未执行。Owner确认后，由原英国现场管理方/唯一容器发布Writer执行；源码窗口只准备候选，不自行操作服务器、DNS、凭据或Actions服务器命令。

| 目标与待核证据 | 最小动作候选 | 影响 | 回滚/停止点 | 责任方 |
|---|---|---|---|---|
| 指定预览origin及入口→英国社区容器路由 | 先只读核DNS、TLS、Host反代与upstream，再按真实根因列最小变更 | 只读阶段不改DNS/入口；后继精确变更另确认 | 保留原记录/证书引用/路由摘要；未核入口归属即停止 | 现有域名/入口管理方与英国管理方 |
| 英国既有主机、容器引擎、cgroup及上述容量字段 | 原管理方经既有通道一次性只读回交当前容器/配额/余量及B5预留 | 不启停、不拉镜像、不重配B5、不新建网络/卷 | 预算不明或资源不足即HOLD；不以缩减B5换空间 | 英国原现场管理方；B5负责人只提供已持有预算回执 |
| 原Center、8类store及现有服务组合根 | 核准确实例位置/创建入口、历史、锁/单Writer、配置与备份；确认英国接入方式 | 不迁库、不初始化、不复制活动SQLite、不读密钥原文 | 历史或位置不明即停止；保留原服务/数据库 | 原客户中心/数据管理方与Owner |
| 英国社区容器启动候选 | 证据齐全后冻结image digest、非root身份、只读代码、独立卷/网络/硬配额、配置/SecretRef与健康检查 | 只涉及社区容器，实际发布仍需Owner确认；不启动fixture server冒充正式应用 | 发布前保留原镜像/配置/卷快照及Writer状态；失败切回准确旧版本，不盲目重试或回写不明数据库 | 英国唯一发布Writer；Owner批准 |
| 英国公益视频容器候选 | 原视频责任方据本表冻结其独立资源/网络/存储/凭据引用，不重做业务 | 不与社区并行启动未获准负载，不另开Writer | 失败只停止/恢复视频项目，不调整社区和B5 | 原公益视频责任方与英国唯一发布Writer |
| request合法域名、真实code2session及原openid绑定 | 由既有管理员核引用与测试身份；变更精确字段另交Owner确认 | 不新建凭据或自动绑定账号 | 未核真实身份即未登录，不关闭TLS/合法域名检查 | 小程序/身份管理方 |
| 同版本HTTPS健康、真机本人资料/门店/订单 | 后端READY且真实身份接线完成后，原上传通道出码并留真机回执 | 国内Runner只执行获准上传/检查 | 后端未READY不上传；健康不等于客户验收通过 | 原上传负责人及Owner验收方 |
| 商户产品资格、真实资金与Finance | 独立提供资格/资金验收方案，本轮不触发 | 不影响源码交付 | 资格缺失payments=false；Finance UNCONFIRMED | 商户/财务/Owner |

这些是待确认的目标与最小动作，不是部署、DNS、凭据或账号操作许可。保留BACKEND_NOT_READY硬门禁；客户预览仍未通过，无英国服务或容器已创建/已部署的声明。

## 证据引用与准确验收层次

- [原英国部署决定](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/76#issuecomment-6162297518)
- [英国归属与原Center现场依赖复核](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/76#issuecomment-6230418580)
- [本次英国容器交接更正](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/76#issuecomment-6313250273)
- [PR133资源精确值缺项](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/133#issuecomment-6281322867)
- [B5取件工具限额，非可分配容量](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/17#issuecomment-6313179688)
- 正式接线源码1ac19e4a564de161ad65c1db6300a9ee4bc9a536，Tree16e3646830fb05a68e7cc7112804eb0cd84216aa，[Hosted39580901541](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39580901541) SUCCESS，1090+342 Python与334+40+8+7 Node合计1821项；含非root Unix代理、真实RSA合成签名接线。不是英国容器运行或真实商户/资金验收。
- 后续仅文档更正不改写该Run/源码包的SHA绑定，不宣称新文档Commit已有同SHA Hosted或已重包。BACKEND_NOT_READY、真实登录/客户验收未通过及Finance UNCONFIRMED继续保留。

## 国内服务复用证据增量

公共大脑、客服中心留国内。实际国内源码的受控bridge、身份模型与社区Center的差异、接口缺项、下一最小改动及域名候选见[跨机接口增量](COMMUNITY_DOMESTIC_INTERFACE_DELTA_20261021.md)。已存在的round-trip不能当身份/门店授权接口；不放宽本地Center类型检查、不挂远端活动SQLite、不迁库或新建身份系统。本节与Owner #6313455771覆盖此前位置待定表述；现场操作仍单独确认。

### 国内身份回交后的范围修正

同SHA国内源码复核确认：消息workflow未知身份会get_or_create_customer创建LEAD，round-trip不是只读身份查询。Resolver仅做渠道映射、可选审计，不是会话/微信验证或租户门店授权；实际认证入口全项目状态UNKNOWN，已核桥接内相关端点NOT_IMPLEMENTED。英国调用许可仍UNKNOWN。准确增量见跨机接口文档，不重新列现场清单；未取得原权威读取合同前不写RemoteCenter或消息fallback，不触发建号。


## 连接之外的预览构建收口（2026-10-21）

依据V27 §8.2.6及原客户开发预览门禁，仅修改 connected 副本准备，不切换现场域名、登录或数据。prepare-mini.cjs 在复制前校验原AppID、项目类型、源码基线、首页和全部已声明页面的JS/JSON/WXML及全树软链；失败不发布输出。副本在同父目录临时准备完成后重命名发布，现有输出及悬空软链拒绝；源目录不写入。此脚本只用于原单Writer构建，不是并发发布锁或现场安装器。

tests/preview_preparation_test.py 从实际生成的 community-stage-source.zip 验证逐文件manifest摘要，解到空目录，以workflow相同源码根cwd执行prepare。覆盖成功非空首页、坏基线、缺首页、错AppID、源码软链、输出悬空软链，未触发上传/微信API/真实身份写入。专用Hosted仅验此6项，未变1821项复用。默认域名仍是历史固定目标；既有uk域名及子路径候选未在现场启用，本次不宣称域名/后端/真实登录/二维码验收通过。


## 既有英国域名子路径离线接线（2026-10-21）

需求依据：V27 §8.2.6、原支付需求“业务终端与页面”1—3、原域名规划 §1—2允许复用已有域名下的路径；Owner要求先完成不依赖云连接的工作。对应缺口是客户端原先拒绝任何HTTPS子路径，而prepare、health和上传脚本分别硬编码旧域名，不能安全选择既有英国入口。

现在共用 deploy/community-preview/endpoint-profiles.json：legacy保持历史默认地址；uk-path-candidate固定为 https://uk.wenwenwenyiyiyi.work/community-preview。仅受保护构建环境的 COMMUNITY_PREVIEW_PROFILE 选择准确名称，拒绝未知配置，不能从客户端请求指定origin。没有切换现场或默认目标，也没有建立DNS记录。session.js只增加该准确子路径，其他任意路径、查询、fragment、凭据、编码路径和非443端口仍拒绝；原根域/本机开发规则保留。

调用链：工作流固定同一个profile→readiness读配置检查精确health URL（无重定向、JSON、READY/connectivity scope）→prepare同profile生成connected副本→上传核prepared app摘要、AppID、scene和目标，并核同source SHA、同profile/baseUrl/origin/health URL且HTTP200的十分钟内健康回执，之后才读取上传密钥。回执仍明确login_verified=false/customer_acceptance=false/payment_enabled=false，不把健康证明升级为身份或客户验收。UNKNOWN或错目标/过期/源码不匹配均拒绝。非connected源码、已有preview.png或receipt.json输出拒绝，防止误用旧二维码或重复提交未知上传结果。

源码ZIP显式包含并要求endpoint.cjs及endpoint-profiles.json；国内解包工作流增加必需输入断言，同时完整保留外层摘要、manifest逐文件SHA、大小/数量/常规文件/路径安全检查。新增测试实际生成ZIP、核manifest、空目录解压并以原workflow cwd执行两种profile的prepare和无密钥上传边界，不只在checkout跑。

nginx-uk-path-candidate.conf仅为既有UK HTTPS server内的两个受限location候选：mini API前缀剥离及精确health，不接管根路由、证书或控制面，继续覆盖原可信来源头。没有Nginx二进制语法验收或现场应用回执；网页工作台全站子路径、TLS/路由冲突及真实原身份/数据运行仍需现场核实，不声称已发布。原MiniApplication、Center SHA/type、身份和门店裁定均未修改。

本次提交使用[preview-endpoint-scope]让Hosted只执行新端点合同、受影响prepare/readiness/候选/ZIP组合与原session/客户页面测试，再构建准确源码包；未变业务1821项复用，不改变普通完整回归或官方上传门禁。未使用[mini-preview]，不触发上传或国内服务器任务。旧本地扩范围执行因root触发既有离线回滚测试保护的记录保留，没有放宽保护。

到此本轮已定位、可离线闭合的端点/构建/上传防错源码已接通。剩余是现场原身份宿主和持久数据/scene配置的权威绑定、实际HTTPS和后端同版本运行、真实微信code2session、合法域名及真机非空业务验收；不得伪造为已通过，也不以空库或我方客服补齐。BACKEND_NOT_READY、payments=false及Finance UNCONFIRMED继续保持。


### 上传前全文件复核补修（2026-10-21）

继续检查发现，前节仅比对app.js摘要，未阻止connected准备完成后其他文件变化。现在prepare对最终副本生成prepared_files逐文件SHA256清单（仅排除回执本身，避免自引用）；上传在健康/版本核验后、读取上传密钥前复核完整文件集合和摘要。改动session.js、首页WXML/样式、增删文件、源码软链及缺少旧版prepared_files均拒绝，不能用只有app.js匹配冒充准确构建。

复核最多2000个文件/目录项、总文件字节10000000，拒绝非普通文件；最终文件以O_NOFOLLOW打开，核stat身份、有限读取长度及前后size/mtime/ctime。清单使用无原型对象，防止特殊文件名遗漏。该预检用于唯一Writer私有临时构建目录，不声称SDK读取期间与其他并发Writer具有原子快照，也不替代外层源ZIP和manifest验证。

测试继续使用真实ZIP空目录解包，并在两种profile准备后修改各文件再调用无密钥上传入口，验证拒绝发生于SDK调用前；新Node测试覆盖特殊文件名、改/增/删/软链及字节/目录项预算。不读取真实密钥、不调用微信或现场身份接口、不生成新二维码。原身份/门店/支付门禁与既有默认目标均不变。


### 受保护宿主配置文件到原应用入口（2026-10-22）

依据原任务正式MiniApplication接线及持久配置要求（Issue76 #6316014038）；原from_existing_runtime只有内存dict输入，缺少宿主既有配置文件到该入口的受保护读取。本轮不创建宿主、身份或数据库，也不生成仅返回HOLD的独立启动器。

实际新增调用链：
MiniApplication.from_existing_config_file(center, runtime, principals, config_path, app_secret)
→ community_mini_host_config.load_protected(config_path)
→ 原from_existing_runtime/validate
→ 原WechatCodeClient及CenterIdentity/MiniGateway。
调用方仍必须提供原客户平台已打开的精确Center/StageRuntime、原Principal和既有AppSecret值；文件只保存原既定schema（version/appid/https_origin/scenes/stores），不含Secret。该接口仅供宿主组合调用，没有HTTP文件路径接口、环境扫描、默认配置路径或自动选择账户。

读取现有绝对路径，逐级目录fd+O_NOFOLLOW拒绝父级/文件软链；父目录和普通文件必须属当前宿主用户且无其他用户权限，文件单链接，最多65536字节。FIFO/目录/硬链接、缺失/相对/越界路径、重复JSON字段、非有限数、无效UTF8及读中变化拒绝，不打印正文。读取后继续原8类store连接路径匹配、原项目当前有效性、CUSTOMER Principal与scene/租户绑定校验，配置错误不会构造提供商客户端。没有自动建目录/文件/库、初始化商家、迁库、写真实身份或打开listener；关闭应用保留宿主持有的8个连接。

新增tests/test_community_mini_config_file.py，复用原合成身份及真实持久SQLite夹具，验证不调用sqlite3.connect/LocalStage、不创建状态、宿主所有权、原登录、未绑定拒绝/不建号、错scene与项目撤权及上述读取负例；另跑受影响原host_config/application测试。真实微信网络仍为明确合成provider，不能当现场真实登录。Hosted使用[host-config-scope]仅验该接点，未变1821项及预览端点55项复用；普通完整回归仍包含新test_community文件。

源码现在可直接消费现有宿主配置文件，但真实客户身份对象、配置路径与历史数据的现场归属仍未证。不能将此入口称已存在的英国bootstrap、已配置原平台身份或可用二维码；既有BACKEND_NOT_READY与支付/资金门禁保持，部署/凭据/权限边界未改变。


## 本项目固定动作及公共连接接入契约（2026-10-22）

依据Issue76 #6320849617与Owner“准备并完成本项目接线”，沿5a5e9369的受保护配置读取、原身份/Runtime组合及21项Hosted继续。公共连接契约核到78e339db的action_binding/private_transfer/SOURCE_CONTACTS；不修改其队列、worker、MCP或接收方鉴权，不将本项目参数当成授权。

### 已有材料与历史/首次初始化的准确区分

| 事项 | 已核源码/记录 | 可以证明及不能推定 |
|---|---|---|
| 客户平台身份宿主 | community_mini_application.from_existing_config_file → from_existing_runtime → 原CenterIdentity；#6316014038、#6320849617 | 原类、SHA/type、账号/会话/绑定规则和保护配置消费已实现；实际客户实例/所在根/宿主组合入口版本仍无现场引用，不能默认等于我方SaaS或国内客服 |
| center | pr122_customer_core.Center在传入root下打开center.sqlite并执行原schema | 原初始化机制存在；不能从构造函数或合成库证明客户旧账户历史或已部署，也不能自行调用它补未知 |
| orders/merchants/ads/refunds | LocalStage.opened对应四个原文件/原opener | 源码可首次创建缺失文件；不是现场已有数据或获准初始化证明。客户首次注册/商家入驻属于原业务需求，真实首次宿主建库仍需明确新实例/空历史事实及原准入 |
| quotes/modules/saas_orders | LocalStage以q=modules.sqlite、s=saas-orders.sqlite组合OfflineSaas(q,s,q) | 八类store不要求八个独立文件，quotes/modules可复用原同一连接；不拆库、不制造数据迁移 |
| scene/门店 | 原config.scenes指向原project/Principal，validate核当前项目/租户，Runtime.bindings保留原tenant/merchant/store | shop1目前只在合成材料中已证。真实project/principal/store必须来自既有保护配置；不能按昵称、手机、客户端ID推定 |
| 现有运行回执 | COMMUNITY_STAGE_HOST_RECEIPT_20261017.json、两机已完成采集、原Issue76 | 只证明隔离测试、元数据和限定扫描；没有客户生产库正文或正式平台运行证明。既不宣称“有旧数据”，也不宣称“全新无数据” |

如果后续权威回执确认从未部署，应明确转为原客户平台首次初始化方案，复用上述原schema/注册/入驻机制；由本项目原Writer冻结准确实例、原密钥引用/备份、首个管理主体和单Writer后走适用准入。不得继续索要不存在的旧实例，也不得把初始化许可从“代码能建库”推导出来。本批没有运行任何初始化。

### 两项实际采集函数与输入

新增scripts/community_connection_collect.py，不含CLI/命令执行/新队列：
1. health()：固定UK hostname；只调用原readiness.check(profile='uk-path-candidate')，精确GET既有域名候选的/community-preview/community/health，不接受调用方URL，不开端口、不调用微信认证。
2. runtime_metadata(plan)：固定UK hostname及community-payment；plan仅从原worker受保护登记注入，恰好含schema/project/config_path/config_sha256/scene_sha256/service_uid/stores。一个现有配置文件≤65536B且完整SHA/scene摘要匹配，8类路径必须与配置完全一致；数据库仅open/fstat/close，绝不read、连接、PRAGMA或运行应用。输出路径摘要、文件元数据与scene数量，不输出绝对路径、身份映射正文或数据库记录。

两项是可执行源码函数，正例离线已运行；目前不是已注册的线上工具。原队列和action_binding.OPERATIONS没有这两个operation，不能改名套用website_baseline_collect、probe或fetch_os_release。建议原连接Writer按自身审核/准入为community_preview_health_check与community_runtime_metadata_collect登记受保护绑定→原队列/worker固定注册→私有报告交付；本项目不添加通用Shell、任意路径参数、临时执行器或修改公共代码。

输入清单deploy/community-preview/connection-inputs.json：4源码文件共19262B，逐件bytes/SHA已固定；清单3024B，SHA256=11f0f7dd571491fbc265aeba600483e43c5003ff27a7c0ff797b3cee439e89cd。它是DRAFT_INPUTS_PINNED_NOT_ENROLLED候选，不能作为private_transfer.Catalog或生产许可。真正source_root_ref/private_result_root_ref/authenticated_recipient仍为null，不能自填可信身份。新输入清单随原source ZIP纳入allowlist/必需文件断言。

原正式运行时输入直接复用5a5e9369/Tree3d5b7c4c、Hosted39633589412，source ZIP SHA39fc2e67c7e3ad6044bee9006c883af776ec89b6b2d41c4e3c91ae4f26a0a882；本批不重跑21项，不把新采集代码说成该旧ZIP已经包含。新采集代码准确Commit/Tree与源码包摘要由本批Issue76/Hosted回执绑定，无自引用版本或旧包冒名。

### 限定路径、资源和结果语义

本项目不提供猜测的宿主绝对根。唯一许可输入为原登记config_path及其stores八类准确路径，禁止目录扫描/动态发现、软链/非普通文件、不安全父目录、权限或完整摘要不符；最多读1份配置，其余只做元数据。文件元数据不是数据库历史/一致性或身份授权证据，报告history_verified/identity_verified/runtime_verified/production_acceptance始终false。

只读动作建议进程预算：CPU5秒、wall20秒、RSS64MiB、单进程、FD32、配置/报告各64KiB；原health的10秒超时/4096字节响应限制保留。这是待登记的有界建议，模块不修改运行worker的rlimit，也没有实际应用额度；由原worker在隔离任务中按准入落实，不能冒称已限额。英国应用仍≤总CPU/内存/可分配业务存储各1/5，实际有限正配额还须扣除既有服务、B5/P2及系统预留。原4CPU/15563716kB回执只是已持有容量时点，不是可分配预算。旧采集不重跑。

结果应私下经原已验证接收方/原Queue SUCCESS/fetch_approved_object/Catalog完整SHA通道交付，报告产出后再冻结其bytes/SHA；本批未预造结果摘要或有效期。当前OS-only MCP不能取本项目报告。公开Issue只记摘要/InvokeId和非敏感状态。连接任务SUCCESS仅证明采集动作完成，不代表BACKEND_READY/身份或客户验收。DISPATCHING/UNKNOWN仅查原InvokeId；SUCCESS不重放，不重投封存request。

### 一次性待核事实与代码责任

| 缺口 | 原出处/现有责任归属 | 下一最小动作 |
|---|---|---|
| 真实客户身份宿主/组合入口版本与config路径、service UID、8类路径、scene/门店摘要 | #6316014038/#6320849617及本文件；现有材料未登记其他具体维护人，本项目唯一源码Writer为窗口4；现场根由英国原管理/连接责任方保管 | 本窗口消费原管理方既有保护配置引用；公共入口支持并获准该限定动作后自行核，不让Owner搬文件，不扫描猜根 |
| 历史数据应复用，或明确为首次宿主初始化 | 原host receipt仅合成、LocalStage/Center源码有建库机制；现场历史尚无证明 | 沿准确原实例/版本与数据保管回执分类；未证时两种情况均不捏造。首次启动由本项目冻结原初始化步骤，仍需适用准入 |
| 两个固定operation进入原队列/worker、结果登记与resource enforcement | 公共连接78e339db SOURCE_CONTACTS明确尚未完成项目动作登记 | 原公共连接Writer按本候选补源码/测试/准入，不能统称外部缺件；本项目不另写公共连接 |
| 受验证recipient与私有源/收件根引用 | PR17 #6328988789/#6329032582，公共接线原任务 | 原公共连接核真实身份来源并登记，拒绝参数/_meta自证；当前null不是可用root_ref |
| UK实际配额/B5预算、TLS/路由和同版本运行 | 已有两机回执和原部署决定；英国原管理/项目准入 | 复用时点证据，缺准确预算/配置集中核，不改权限/部署以试探 |

本窗口当前已通过真实只读插件connection_status查询既有conn-uk-20261021T151122Z，返回SUCCESS/t-gbr70pxt9ij2jgg，production_authorization=NOT_GRANTED；没有新任务/重试、没有从OS结果读取客户文件。仅证明本窗口旧状态工具可用，不能代替上述项目动作/私有收件。

后继验收顺序：公共固定动作正常准入→本窗口自行取私有报告并核SHA/原InvokeId→按事实绑定原宿主、持久数据和场景；如首次启动则走原批准初始化→英国同版本服务、精确HTTPS/路由、原平台真实code2session→原官方上传通道→真机非空页面与本人/门店/订单权限。每层分别报告。BACKEND_NOT_READY、payments=false、Finance UNCONFIRMED保留。没有服务器命令、权限修改、微信/资金调用或后台持续运行声明。

## 首次上线确认与原持久运行组合（2026-10-22）

Owner已明确确认本客户平台“首次上线，无历史数据”（原Issue76 #6329634311）。本项目不再把旧客户库/旧身份宿主作为必须寻找的外部材料；原文历史UNKNOWN仅保留为当时记录。首次初始化仍不同于测试fixture，也不等同于真实账号/门店授权已存在。Owner同时确认原AppID wx1d5f8873eaea5392及验收微信开发者权限；所交小程序后台截图显示服务器域名尚未配置，英国8.208.119.115已在IP白名单。IP白名单不等于request合法域名或HTTPS连通。

原LocalStage明确是测试宿主，会生成测试QR密钥和LocalAdminPolicy随机令牌，禁止部署为客户后端。本批新增scripts/community_persistent_runtime.py中的PersistentRuntime，替代这部分宿主职责而不修改原StageRuntime、Center或门店裁定：
- initialize(directory,bindings,clock=...)仅用于已获准首次安装，准确绝对新子目录及既有0700私有父根；沿原6个物理store opener/schema初始化，复用quotes/modules同一连接，不种子账号/商家/商品/订单，不生成管理令牌/QR密钥，不开listener/网络或支付。
- open(directory,bindings,clock=...)仅打开已有完整当前schema数据，mode=rw，缺文件/锁拒绝且不补建；逐件原schema及integrity/外键检查，不调用初始化/迁移/自动修复。未知或旧schema停止，不能假称支持自动升级。
- 原CUSTOMER/tenant/store绑定校验先于写入。原flock单Writer持续到句柄关闭；准确路径、父链、0700根、0600类私有单链接普通文件和SQLite sidecar校验保留。可信同UID私有目录仍要求原唯一Writer，未宣称抵御已控制该UID的并发攻击者。
- 初始化失败关闭句柄/释放锁，部分文件原样保留，不删除或自动重试；已有目录即便空也不能重新initialize。初始化不是跨6库原子事务，也不是恢复/迁移工具。Center及其原加密/备份仍由单独宿主负责。
- runtime为精确原StageRuntime，原DemoService仅复用为store容器且admin_policy/qr_key均None，没有启动demo HTTP或开放本地管理令牌。正式MiniApplication必须继续配置原Commerce，服务端定价/原身份门禁不能由初始化取代；不调用模拟订单/支付钩子。MiniApplication.close不关闭该宿主持有的连接，宿主负责最终close。

新增tests/test_community_persistent_runtime.py的8项定向测试使用合成身份和真实私有SQLite，包含独立Python子进程重启读同一订单、第二Writer/重初始化、缺库/未知schema不修复、初始化中途故障保留、软链/硬链接/公开权限、无数据/随机凭据，以及原MiniApplication+Commerce同对象组合。初次本地失败为测试传入空operations grants，原门禁正确拒绝；改用既有合成原授权夹具，未放宽生产检查，原失败日志保留。真实微信网络/现场账号未调用。

本次仅交首次持久运行宿主源码，不称完整正式bootstrap已完成：原Center首次注册/验证及可信微信绑定、首个真实项目/scene/门店业务配置、既有受保护密钥引用、英国资源/HTTPS和实际启动仍需按具体首次上线方案完成。不得直接SQL设verified或伪造签约/项目authority；不得把我方SaaS身份变成客户平台数据。现有公共连接代码不改，人工辅助现场动作需先交准确可审阅方案，尚未发服务器命令或执行初始化。

Hosted以[persistent-runtime-scope]验新8项和实际ZIP组合1项；原21/55/1821未变结果复用，源码包仍走原逐文件manifest。准确Commit/Tree/Run/包摘要见原Issue76后继回执。BACKEND_NOT_READY、payments=false、Finance UNCONFIRMED保留，尚无可用新二维码。
