# 社区预览正式后端接线与现场依赖

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
