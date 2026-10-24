# UK preview 五项固定对象只读取证候选：供根独审，未执行

沿Issue76与唯一社区Writer。复用b09b837b338def5db8485bda8c4fa4e98d98139f / Tree
0ca7e21daf9268e276c4356ef68932c367f57b78（24项+根2边界scopePASS）、a932控制器及
f131产品。新代码只扩充离线只读取证候选，不调用composition、不建立Journal、不执行旧升级器。

## 已有成果可复用及真实不足

原 scripts/community_preview_version_inspect.py 为21615B，SHA
98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3；对应原shell22121B/
171c682e92e2c18bb7b3a5fb1414c491e9a93fc72a069112314834135e95ea0f。
旧保护读取、bounded capture/timeout kill+reap、固定匿名HTTPS probe与typed image投影复用，
不重写或全重跑旧套。原脚本不含当前完整隔离四摘要、新socket私有health、新approval/journal父
metadata或固定f131加载观察，故不能仅拿旧脚本称五项完成。

新薄层 scripts/community_preview_preupdate_observe.py，离线生成器
scripts/community_preview_preupdate_bundle.py 生成两份自包含原件：

- deploy/community-preview/preupdate-five-readonly.py
- deploy/community-preview/preupdate-five-readonly.sh

生成器锁原observer、b09 composition、原upgrade准确SHA；原observer完整只读模块在内存载入，
从b09逐AST节点原字节提取require/digest/stable_metadata/inspect_bound/PRIVATE_PROBE，
从原upgrade只提取ROOT/RUN/INSPECT_FIELDS/Rejected/validate。没有带入upgrade.main/mutate/
resume或composition/Journal执行器。runtime无需安装源码、联网下载、写临时模块或改sys.path。
常量/函数不是另维护的第二套权威源；上游pin变化即离线生成拒绝。薄层body纯新增取证投影。

准确原始bytes/SHA/mode统一见preupdate-five-readonly-manifest.json；shell嵌入Python必须逐字
匹配，不能Owner自行拼接。正文不给任何现场命令或执行指令；本轮仅将原件交Owner/根审阅。

## 五项一次固定范围与输出

| 项 | 真正采集的固定对象 | 有证输出与不能声称的事项 |
| --- | --- | --- |
| ① current | 固定NAME xuanjun-community-preview→窄ID/image→按观察到的准确ID完整隔离验证、image OCI；原config目录/三个参数文件、data目录/runtime目录metadata；原两路由文件摘要 | current ID/image/OCI/running/User，四个与b09同算法摘要；第五backup_reference_sha256明确UNKNOWN，不能造完整current准入tuple |
| ① 名称 | 仅固定NAME及由f131+观察旧ID派生的唯一before/failed名字，三次精确锚定名称查询 | 成功空查询可OBSERVED_ABSENT；存在则准确ID/image/running与Name复核；daemon/权限/输出异常UNKNOWN；不列全机容器或重查旧rollback |
| ② socket/health | /run/xuanjun-community-preview/preview.sock元数据；同socket GET /community/health；匿名HTTPS https://uk.wenwenwenyiyiyi.work/community-preview/community/health | 原socket为project UID/0660（原nginx组），父链保护，前后inode/owner/mode复核；真实状态/版本/远端时间与本地采集时间分开；缺远端时间仍UNKNOWN，不把HTTP200算同版 |
| ③ root安装/审批 | 原/opt/xuanjun-community-preview与已证roles-upgrade-2330dd55目录metadata；固定 proposed update-approval.json和update-journal父metadata | 输出实际owner/mode/type/inode，审批需0600、journal父需0700，未具证不MATCH；原root caller各源码确切安装路径未有证，逐文件expected repo SHA与observed path/SHA/owner/mode UNKNOWN，不猜路径扩扫 |
| ④ image | 只image inspect固定release sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a | 精确ID、OCI、User、RepoDigest摘要；match仅指已加载元数据与f131相符，不是部署；inspect失败UNKNOWN，不能把非零退出猜成未加载 |
| ⑤ backup | 唯一已知/roles-upgrade-2330dd55/include.before仅metadata；真实data备份路径/摘要/恢复与降级证明原记录未有证 | include.before只标ROUTE_BACKUP_ONLY；DB备份reference/sha/restore/downgrade全UNKNOWN；不扫目录、不读客户/DB/config/secret正文、不自行备份、恢复或制造证明 |

原两路由仅/etc/nginx/community-preview.inc和/etc/nginx/conf.d/xuanjun-p2-owner.conf的
受保护metadata/hash，后者不输出正文、不读取P2运行/数据、不reload配置。原config三个文件为
/var/lib/xuanjun-community-preview/config/host.json、center-keys.json、wechat.json，只有
metadata，不读正文。数据只固定data目录metadata，不枚举或读数据库/材料。目录mtime/size不充
稳定身份，四摘要算法与b09同源。备份引用未提供就不能计算第五摘要，更不能以路由备份代填。

## 原来源与尚缺项的准确结论

历史真实部署回执Issue76#6333101186：工具f5f6492ce827aa8cd9273f37bd9742190570f2f1，
旧产品2330dd55c07f58d7f45a7c4510a9761d0d4735d6、原数据配置复用、旧容器保留；它没有给
当前新鲜准入、DB备份恢复证明或新root composition安装位置。根03:00观察的OCI准确是
2330dd55c07f58d7f45a7c4510a9761d0d4735d6，不能把两个历史字符串归一或冒当前image ID。
这些历史来源已核，不在本候选重复读取旧attempt/resume receipt或旧rollback。

root caller可能历史通过内存脚本执行，但没有准确持久安装路径证据，不能推定已安装在stage下
某个.py。候选不会find/rg/listdir/rglob或docker exec去寻找。原连接窗口后续若给准确既有路径与
证明，可再独审该最小固定来源；本轮不把“没有路径资料”误称现场不存在。第五项无恢复证明且
只读不能建立证明，准确保留外部缺项，不要求Owner猜ABI/路径/哈希。

f131已核产品receipt保持原样：Run40059478387 / Job120769700068，artifact12546452389，
outer57016858B/c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e；
inner57365044B/eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875；
source f13155ed63a3137d41766ee587d9b4b96a81477f，User10001:1008，stamp0444，11层独验复用，
有效至2026-10-27T03:44:30Z。只查是否已加载，不下载、不load/构建/pull镜像，不改产品stamp。

## 安全边界、总量与退出

固定主机iZd7oeikknn1z21sq6ji6zZ，UID/EUID均0，无参数；不符在采集前exit2。
原no-follow dir-fd父链、owner/mode/type、单链接regular文件、有界读取、读前后inode替换
校验保留。socket有专门stat-only验证，不作为regular文件open/read。

原capture对子进程stdin DEVNULL、固定PATH/LANG/DOCKER_CONFIG无凭据上下文、有界双pipe、
独立process group、超时killpg/reap；Docker观察8s/最大32768B（名字/image4096B），health子进程
10s/10000B、body4096B；总体90s（另原kill/reap最多2s），JSON最多32768B，shell只附退出码。
匿名HTTPS复用禁proxy/redirect/TLS/JSON原probe；private仅原socket原GET。网络/daemon/权限/
解析/时间不明均HOLD/UNKNOWN，不原样转发错误、HTTP body、嵌套值、Docker完整JSON或Env。
DockerCLI/daemon内部可能读取Env，**只有传入Python与日志的固定白名单无Env**，不作更强宣称。

当前与socket采集后复核，不宣称跨filesystem/Docker/HTTP原子快照，snapshot_atomic=false。
由于根caller安装和backup证明缺失，程序始终exit2/HOLD，production_acceptance=false、
preview HOLD_NOT_EVALUATED、execution_permission NOT_GRANTED。这不等于采集失败，也不
等于原controller拒绝真实KNOWN_FAILURE恢复；两者范围完全不同。

## 下一次一次性只读取证许可范围（尚未请求Owner确认）

先根独审本包准确SHA/bytes与下列范围，再向Owner**一次确认仅此只读采集**：

1. 原UK既有root执行路径/既有身份；准确审结self-contained Python或shell其中一份，固定
   bytes/SHA，单次、90秒、最多32KiB输出。不能改代码、变量或参数、换主机/入口/另建执行通道。
2. 允许上表①—⑤中已知路径的metadata、两路由hash、固定白名单Docker只读inspect/精确名称ls，
   与固定匿名HTTPS/原socket GET；不包含未知caller/backup路径搜索、任何私有正文/服务写入。
3. 脚本本身不新建目录、文件、临时包、lock、approval/journal、不加载镜像、不stop/start/run/
   rename/pull、不做备份/恢复、不改权限/账号/secret/config/路由/服务、无self-hosted dispatch。
4. 报告缺项/exit2不允许自动重试、扩扫或升级成更新许可；保留原始回执/时间/准确候选版本，
   没有InvokeId不能编造InvokeId。本轮无现场调用，SITE_NOT_EXECUTED。

## 未来600秒 same-attempt实际更新许可仍必须具备的完整集合

只读取证的同意**不包含以下实际更新许可**。未来一次精准更新必须冻结：新鲜准确current
ID/image/OCI、四摘要+真实backup第五摘要、source/Tree及固定f131产品receipt、准确待用
controller与b09 composition bytes/root安装载体、原真实备份引用和已核恢复/降级兼容证明、
root0600审批digest/issued/expires≤600秒/backup_verified_at、root0700固定journal父及
同plan/attempt完整history/排他锁、已加载准确imageID/OCI/User、按PREPARED或KNOWN_FAILURE
阶段对应的准确NAME/rollback/failed ID归属。执行时原guard再核有效期和单writer，不能拿latest
替换人工所见tuple；UNKNOWN保持HOLD，不无条件一次更新。

当前caller/backup缺项无法凭一次只读造出，因此不能预签上述更新许可。镜像加载、父目录
若需建立、源码安装、备份恢复各属于必须具体批准的独立动作，不包含在本次read-only许可。
不触及P2/官网/币安，不上传微信或证件、不启用生产OCR或支付。

## 验证

仅新14项隔离测试，复用原b09/a932及原observer旧验收，不跑旧24/46或模型/图片。测试使用
真实临时目录和文件投影；Docker/HTTP为明确合成frame。当前本地OS拒绝创建Unix socket
（EPERM），已停止该动作，不重试/换入口；socket元数据为明确合成stat夹具，未创建socket/
listener或把它称现场读取。覆盖无私有正文/扫描/写入、四摘要同源、第五UNKNOWN、固定名称
成功空查询与异常、远端时间缺损/陈旧/类型、嵌套/重复/超限JSON、socket type/mode/symlink、
current变更、镜像未知、root/参数门禁、总超时/信号恢复和self-contained生成实际投影一致。
AST3.6与bash -n验证的是候选兼容语法，不是UK宿主已执行或网络/安装验收。
