# 05:26:43Z真实UK回执后：纠错、三对象原因、安装/载入和备份准备

仅Issue76源码与方案，不执行服务器。本轮不备份、不load、不建现场目录/改权限/部署。
cec5五项只读候选已经根scopePASS且Owner于2026-10-24T05:26:43Z实际执行，内外exit2；
不能继续写待执行。原始完整回执根持有，本窗口只用已给非敏感事实，不访问受限附件。

## 1 严格OCI纠错，不是现场改变

实际current：container818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c，
image sha256:0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32，
OCI2330dd55c07f58d7f45a7c4510a9761d0d4735d6。Git只读核实该commit存在、Tree
 d89428ae6f0ba2e990f4c58a0dc28975271da497，与Issue76#6333101186相符。

planner最初b9a1732把串误写为2330dd55c07f58d7f45a7c4510a97610dd4735d6。
本轮只把OBSERVED_OCI固定到真实完整串，旧错串仍被严格拒绝；没有strip/归一/前缀匹配或
接受多个版本。更新composition中planner文件pin、readonly生成器及公开pin、派生manifest。
a932 controller文件不改；f131产品源码/镜像/receipt不改、不重建。历史Git与原回执不覆盖；
当前六份说明中的旧文字转录同步纠正，不能再拿旧文字声称03:00/05:26现场版本发生变化。

current config/data/route三个摘要根已重算一致，socket前后MATCH，两候选rollback名字ABSENT，
全部复用，不重取。本轮不拿05:26快照当未来600秒执行准入，临近真实更新才统一刷新并冻结
同attempt tuple。HTTP200/READY仅process+DB；runtimeSHA/时间UNKNOWN，仍非f131同版验收。

## 2 三HOLD失证原因：已定位的源码事实与未确定现场事实分开

cec5 collect捕获所有Exception后仅写HOLD_UNKNOWN，丢了code/stage，故仅凭回执无法判断
current_recheck或f131 image inspect是timeout、CLI拒绝、解析异常、还是严格字段比较变化。
OCI planner错串不在cec5 current_projection比较路径中，不能把这两处HOLD都归因于笔误。

private probe存在确定的协议缺口：原composition.PRIVATE_PROBE继承root进程，没发送原
X-Xuanjun-Client-IP。原TrustedNginxSource先校验SO_PEERCRED的既定nginx UID，再要求唯一
私有代理头。原历史community_preview_upgrade.HEALTH_CODE相反，明确降到原UID/GID1008并
带固定127.0.0.1头。新隔离测试用原trust类精确AST复现root peer被拒、匹配peer但缺头仍拒。
这是源码级可预见拒绝，不等于已核这次现场private HTTP403；实际响应码仍UNKNOWN。
不为跑通而改服务端权限、改reader恒真、冒充登录或自动改peer身份。

必要的原因取证候选只准备以下三个对象（不执行）：

- current_recheck：复用原current投影读取两次，输出阶段枚举/受控reason，成功则仅输出变化
  字段名与固定ID/image/OCI；不重新打印整套config/data/route、不做五项总采集/名称/socket调查。
- f131 loaded：只固定571b7c6e…release image inspect，COMMAND_REJECTED/TIMEOUT/结构枚举；
  失败仍UNKNOWN，不以此猜未加载或服务失败。
- private health：只原socket同GET、root/no IP header身份保持不变，允许记录403等HTTP状态；
  只投影PROXY_DENIED/ORIGIN_DENIED/NOT_FOUND等有限error enum，绝不输出任意HTTP正文。

三对象脚本three-reasons-readonly.py/.sh是自包含定稿，由原离线生成器产生；无新入口/权限/
凭据/服务。70秒+原kill/reap最多2秒，总JSON16KiB；原process pipe预算与超时回收保留。
固定UK root/no-arguments门禁，始终exit2/NOT_ADMISSION。没有异常文本或stderr透传。
本轮不向Owner发现场命令或索其重跑；只有根审后另具体批准才可沿原路径单次运行这三对象。
在原peer身份读回契约与实际私有响应未证前，生产private health仍HOLD；不是服务故障结论。

## 3 不再等待未安装对象：准确拟安装载体与持久影响

原approval与journal父路径这次确实MISSING；原root caller installed_path是脚本设计UNKNOWN，
不是它已经检查过某个具体文件。现在准备新的明确目标，而非继续索要不存在旧安装证明。

拟root载体：/opt/xuanjun-community-preview/control-oci2330-v1。
离线public archive control-oci2330-v1.zip及manifest已经生成，未上传服务器/未安装。
archive不含业务数据、secret或镜像；manifest逐文件bytes/SHA/uid/mode是安装规范：

| 拟路径（均在上述固定根下） | 来源/作用 | 目标owner/mode |
| --- | --- | --- |
| loader.py | community_preview_root_loader.py | root:0600 |
| manifest.json | 离线精确清单，由根审结SHA | root:0600 |
| scripts/community_preview_release_plan.py | 严格OCI纠正后的planner | root:0600 |
| scripts/community_preview_update_checkpoint.py | 原a932原字节 | root:0600 |
| scripts/community_preview_update_composition.py | 原b09算法，planner pin更新 | root:0600 |
| scripts/community_preview_upgrade.py | 原transport原字节，绝不调旧main/resume | root:0600 |
| scripts/community_preview_version_inspect.py | 原readonly helper原字节 | root:0600 |
| deploy/community-preview/f131-image-receipt.json | 已审冻结receipt原字节 | root:0600 |
| 所有本载体目录 | 仅新路径，已存在即HOLD不覆盖 | root:0700 |

loader是具体代码：验证root/UK/manifest SHA；固定文件集、nofollow父链与leaf、root模式、
单链接/大小/读前后identity、全部文件SHA通过后才在独立进程内加载原模块定义；不修改sys.path，
不允许已存在scripts命名空间混入。读取可更新atime，不把atime当内容改变；mtime/ctime/inode/
mode/owner/size仍严核。默认CLI只返回HOLD，不执行compose/run/recover，不创建Journal。
未来root调用方仍须准确审结manifest digest并显式调用load；载体安装不等于更新许可。
已补独立进程真实临时载体加载、篡改/symlink拒绝测试；这是隔离临时安装，不是UK已安装。

未来需另外具体批准的持久动作一次列明：创建此载体新root0700目录并安装上述root0600公有源码；
建立固定/opt/xuanjun-community-preview/update-journal root0700；安装root0600
/opt/xuanjun-community-preview/update-approval.json（仅临近执行填真实所见tuple、digest和600秒
有效期，不现在造空审批）；可能的镜像stage/import；另述完整备份/恢复验证目录及维护窗口。
不复用空账本冒历史：journal路径确missing才可经批准新建，有现存/冲突/部分历史则HOLD，
不覆盖旧stage、旧rollback、账户/config/data、Nginx/P2/官网或秘密。无新增systemd/常驻服务。

## 4 固定f131镜像载入方案（尚未获准/执行）

产品仍f13155ed63a3137d41766ee587d9b4b96a81477f / Tree
c31a9b1df006eeacd78ae3f9921073f3fe77d2c3。Run40059478387/artifact12546452389已审，
outer57016858B/c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e；
inner57365044B/eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875。
release image sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a，
OCI=f131/User10001:1008/stamp0444/11层已核，artifact有效至2026-10-27T03:44:30Z。
新控制源码提交绝不是该image source，不重建或重tag冒同版。

拟仅镜像输入stage /opt/xuanjun-community-preview/image-f131-40059478387，root0700、
archive/receipt root0600；既存冲突HOLD。沿原已授权运输方式接收准确原artifact，不新下载通道/
secret，不从受限附件改名搬运。载入前先核outer、inner长度/摘要及层/配置、Linux amd64、
可用磁盘/inode预算、artifact有效期；先观测固定ID，已经准确加载则复用，不重复import。
若尚需import，须Owner独立批准原Docker socket的单次load准确archive；无pull/构建/run/stop/
start/rename/端口/服务变化。导入回执后窄inspect ID/OCI/User与固定值匹配才算加载完成。
超时/返回不明不盲重load，HOLD同操作回执。当前loaded状态仍UNKNOWN，不能预填NOT_FOUND。

## 5 固定数据集完整备份/恢复/降级方案：未执行、不是已有证明

原受保护挂载两个根是已证范围：/var/lib/xuanjun-community-preview/data（含原Center身份/
对象/业务持久历史）和同根/config（host.json、Center解密key引用/原Wechat配置及其他既有
原文件）。runtime socket目录是临时状态，不作DB备份；include.before只备路由，明确排除作
数据恢复证明。固定全集复制两根而非臆造某个DB路径/漏密钥；实际数据库路径只能由原受保护
配置/宿主store manifest私下核，不输出配置正文/客户资料或推断猜测。备份任务一旦授权会读取
这些敏感数据，与本轮只读取证许可是不同权限范围。

拟新的独立backup/restore审查根：/opt/xuanjun-community-preview/backup-2330-to-f131-v1，
root0700；snapshot、private-manifest、restore-old、verify-f131、verify-downgrade均为新子目录，
不覆盖既有目录或活动data。每个相对文件路径/类型/uid/gid/mode/size/SHA记录在私有root0600
manifest，解密必要config同等私密保留；公共回执只记manifest摘要/计数/总量及有限结论，不打印
秘密/数据库正文。不得公开备份包、不生成新加密key、不将未加密私有包推GitHub。

最小完整阶段及停止条件：

1. 先另批备份窗口/唯一Writer/准确旧container+image与两根身份、容量/文件数/总量硬预算、
   原有写入冻结方式及解密key保持责任。原Center维护状态+无listener/未提交事务是
   community_stage_recovery.snapshot的前置，它只覆盖原六业务库、不含Center，也不能直接
   拿来备份现在的PersistentRuntime；本轮不改为绕开类型检查。没有已证冻结入口就停止，
   不在活跃SQLite上普通cp/tar，也不假设停止HTTP就停止所有writer。
2. 取得准确冻结/连接关闭/WAL及全部writer静止事实后，在一个受控窗口复制上述完整固定数据集，
   保留原owner/mode；拒绝symlink/hardlink/设备/跨根目标，所有文件与目录fsync、manifest原子
   发布。任何未知或空间不足保留本attempt失败证据、停止，不删历史/盲重试。冻结窗口及所需
   stop/start是未来真实持久动作，**当前controller没有备份阶段hook，不能声称已接通自动备份**。
3. 恢复到全新隔离restore-old；逐文件摘要/manifest验证后，仅由已审原宿主核真实store绑定，
   对全部SQLite做只读integrity/foreign-key检查，核Center对象/key关联及必需加密记录可读（不
   吐字段正文/身份）。若WAL需要恢复，应按原SQLite恢复合同处理并验证，不能忽略WAL或只看
   单DB PRAGMA。原始snapshot保持不动，验证针对副本。
4. 用准确旧image在隔离clone做旧版本恢复启动验证，禁外网/付款/OCR、独立socket与clone挂载，
   不挂活动data/config。再从同一已验副本创建verify-f131，由新固定image打开/必要原迁移；
   最后在新的verify-downgrade副本核旧image读取新schema/关键业务语义是否兼容。
   health200仅连通，不是恢复/降级通过。旧image无法接受新schema则downgrade=HOLD，不承诺
   直接start旧容器即可回退；实际数据恢复/切换需额外精准批准。
5. 验证结果和独立审结形成既有root0600单链接backup-reference.json，写入准确snapshot/manifest
   digest、旧/新source+image、已验恢复/降级结论和验证时间。仅此真实来源可供composition
   backup_reference(fd)绑定第五摘要；不能把本方案/fixture/签字空字段当成备份证明。
6. 只有实际更新临近才统一刷新600秒current+backup时间、同attempt人工所见完整tuple和审批。
   备份后若旧服务继续有写入，备份不是当前回退点；必须保持已审维护冻结，或另批最终一致性
   备份。当前缺真实冻结/备份/兼容记录，不能提前宣布该阶段可自动执行或放行更新。

这里只交完整方案与具体待批数据读写范围，不运行任何上述阶段，不索Owner重跑5项。
不能把“源码可加载/方案已准备”当真实备份、恢复演练、同版health或更新成功。
