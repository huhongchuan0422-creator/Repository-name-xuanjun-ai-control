# 原更新验收契约：单次固定匿名HTTPS + 受保护宿主前后绑定

Owner于05:57:02被问及以固定HTTPS经真实Nginx、严格容器/镜像/路由及远端版本时间验收，
05:57:29明确“确认”。此许可仅改源码契约，不是现场读取、部署、数据写入或生产OCR许可。
基线be5dc3a92948ccd29be254361f2d26f7f3d96860的OCI纠错、root loader及21项证据复用。
a932 controller/原权限/f131产品镜像均不改、不重建。

## 消除矛盾，不伪造代理

旧actual_health强制PRIVATE_PROBE成功，但该probe是root/no私有头，服务先核真实Nginx
SO_PEERCRED与唯一X-Xuanjun-Client-IP，故会阻断。这不是服务故障，也不是切身份/伪造头
或放松服务端权限的理由。现在actual_health无受保护上下文直接拒绝、零HTTP；compose
仅在完整原Journal成功打开之后安装BoundHttpsHealth(journal, original LiveBindings)。
PRIVATE_PROBE常量只为旧只读诊断/历史测试保留，绝不由更新验收调用；旧只读包中private
观察字段不是新验收契约，不声称独立“双路”。

## 唯一响应来源

一次且仅一次 GET：
https://uk.wenwenwenyiyiyi.work/community-preview/community/health

复用原HTTP_PROBE：正常TLS验证、固定URL、禁redirect/proxy、application/json、4096B
body、10s child/10000B pipe、原bounded kill/reap。客户端只有原Accept头，不发送私有
代理头、Authorization、cookie；不setuid、不伪SO_PEERCRED/credentials、不直连socket
读健康、不复制公网响应或重复请求冒双通道。真实Nginx依原配置和原peer权限转发。
这份响应是单一链路的观察证据，不是密码学远程证明或跨系统原子快照。

## 前后绑定的原来源与判定

BoundHttpsHealth只接受原root composition提供的真实Journal和原受保护LiveBindings。
每次调用清空last_evidence；从已持久Journal冻结phase/new_id/sequence/plan_sha，不从HTTP
body取得ID/权限。固定plan完整fingerprint、journal owner线程及非poisoned状态前后必须一致。

请求前和响应后分别核：

1. 原LiveBindings重读原Center外部宿主配置/数据/路由/备份reference来源，原审批/源码pin/
   600秒期限仍适用。current所有键、类型和不可变字段都须与批准tuple一致，observed_at真实
   新鲜、running按阶段；没有cb/缺任一字段/不符均UNKNOWN，不能裸公网fallback。
2. 持久准确new_id必须与旧ID不同，按ID窄inspect准确旧/新image及原资源/mount/nonroot/
   无published port/device/capadd。NEW_KNOWN时old stopped/new running；原恢复最后阶段
   RECOVERY_START_OLD_INTENT时old running/new stopped。其他phase拒绝，不自动恢复/重试。
3. 固定NAME xuanjun-community-preview再解析必须是本阶段准确target ID/image；image窄
   inspect的ID/OCI/User10001:1008必须与固定产品或原旧image相符。新验收只能固定f131。
4. 两个原路由受保护摘要都等于批准current.routing_sha256；community-preview.inc还必须
   等于原已审original.FRAGMENT的准确SHA（不归一/模糊匹配）。共享vhost只算固定文件摘要，
   不吐正文、不操作P2。前后路由不变才可接受，错路由/替换/失证UNKNOWN。
5. 原/run/xuanjun-community-preview/preview.sock只stat，不连接：nofollow父链、原project
   UID10001/GID1008/0660、单链接Unix socket、parent/path前后复核。两次socket的device/
   inode/owner/group/mode/mtime/ctime必须相符；缺失/类型错/重建/权限变化均UNKNOWN。
6. 响应后再核审批/Journal/时间与上述绑定完整相等。clock倒退/远端observed_at在耗时宿主
   复核后跨600秒或未来>30秒，拒绝；绝不以本地采集时间回填远端时间。

新版本必须真实返回runtime_source_sha=f13155ed63a3137d41766ee587d9b4b96a81477f、
version_source=IMAGE_BUILD_STAMP、integer observed_at（拒bool/float/缺失/陈旧），且与本次
准确image OCI一致；scope=PROCESS_AND_DATABASE_CONNECTIVITY、production_acceptance=false。
旧2330的public200 READY但无版本/时间一律不能用于新验收。错SHA/stamp/source/binding
抛HOLD，由原controller落UNKNOWN，不变成可自动恢复许可。

完整且已知的新版本MAINTENANCE/UNAVAILABLE响应仍交原controller作明确失败判定，不能
拿其当READY。该判定不自动调用recover；完整same-attempt KNOWN_FAILURE和新停事实等
原恢复约束不变。任何来源不明不应调用恢复。

## 旧镜像恢复边界

恢复使用同一匿名HTTPS入口，前后绑定准确old target/image/真实旧OCI、新停及原socket/
路由。不能把新SHA当旧SHA。旧响应若真实没有runtime/stamp，最多是LEGACY_ROLLBACK_
PROCESS_DB_ONLY，不能称新同版；若部分给出或互相不符，UNKNOWN。原a932还要求恢复
健康的真实远端observed_at新鲜；旧2330没有这个字段时，保留HOLD，不用HTTP Date或本地
时间伪造。恢复可能已按许可启动旧容器，但这不等于恢复验收通过，更不证明数据可降级。

## 可审证据与测试

成功的BoundHttpsHealth.last_evidence保留contract=ANONYMOUS_HTTPS_ORIGINAL_NGINX_PATH、
independent_private_health=false、准确target ID/image/OCI、宿主绑定摘要、请求前后时间、
原远端时间与source字段、明确scope。仅完整核验成功后设置；任一失败清空，不能复用旧成功。
原Journal schema/数据库不扩展、controller原字节不动；是否把结果写入原发布回执仍依原批准。

测试代理结果/Docker/host/socket元数据均为明确合成fixture，真实临时route文件、完整Journal、
线程/锁/跨进程重开与controller链实际执行。无真实socket建立/服务/HTTP/UK调用。新增16项
验收测试，另受影响composition25项（含新缺runtime整链UNKNOWN负例）合计41；不重跑旧21、
模型/OCR算法或66图。覆盖单次请求、零private/无头/无身份切换、无上下文拒绝、old200无版本、
错SHA/stamp/time、响应后跨期、路由/容器/OCI/socket变化、Journal代次/绑定变化、真实类型保护、
旧恢复边界、跨进程KNOWN_FAILURE恢复及missing runtime不准恢复。

## 版本与现场剩余条件

只改composition契约、必要测试/说明及精确pin/生成资产/公有root载体manifest。既有loader/
OCI严格纠错、f131镜像/root存储权限不改。派生readonly历史脚本只因composition精确文件pin
更新而重新生成，并没有再次现场执行。前版证据继续只证明其当时SHA，不冒新SHA CI。

Owner05:26:43Z已执行的只读回执保留：准确旧container818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c，
oldimage0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32，
OCI2330dd55c07f58d7f45a7c4510a9761d0d4735d6；三摘要/socket/名称旧事实复用，不拿它充新鲜准入。

实际现场仍需原root载体安装与准确hash/owner/mode、fixed journal/approval、真实数据备份/
恢复降级证明和冻结窗口、固定f131已加载ID/OCI/User及新容器持久ID、正确路由/socket和真实
runtime/time响应；临近实际更新才统一冻结600秒same-attempt tuple并具体批准。
本轮零服务器/取证/镜像载入/停启/建目录/权限变化/部署/微信上传/生产OCR或支付。
