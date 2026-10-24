# 原阶段A完整交付候选（仅送根审，现场NOT_EXECUTED）

原3b6be4aa1ff06d088fe26f44f08b9a505c5b5513 / Tree cdd9ae50d91d65cebac79897a414ff4d9a6032ec
两修44项及独审SCOPE_PASS直接复用。原caller/wrapper字节、b789/core、111330B载体及f131
镜像均不变；本轮仅修a89新增外壳的TTY调用形态、内部完成JSON校验及对应联验/证据；原适配入口字节也不变。

## 1 一包四输入与固定目的地

本地已实际生成单包 `ISSUE76_STAGE_A_94326ff1f3eb.zip`，57179504B，SHA256
258ce847ff8b3e4b2046a35c99ced9cf1b9011a523ea802a77e59c657cccca43。
六个ZIP成员=下列四个**公开业务输入**+stage-a-entry.py管理入口+manifest.json元数据；不是
六个业务输入，不含秘密/config/DB、原私有资料、credential或新镜像。ZIP_STORED不改原制品。

| 四输入 | bytes | SHA256 |
| --- | ---: | --- |
| community_preview_site_prepare.py | 32470 | 48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55 |
| prepare-site.sh | 3642 | f1af825d4acec6d775956a16a19f5e65b3a58c6aae0e703164f84ee9429ba2c6 |
| control-oci2330-v1.zip | 111330 | aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9 |
| artifact12546452389.zip | 57016858 | c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e |

原f131 artifact来自Run40059478387，之前正常GitHub取回且根已独验。本地旧原件再核精确长度
与原摘要后直接装包，没有重建/重跑镜像。内层tar57365044B/eb7045414ced005a56158ac7eb54519098ec8a9e9da5589f939a0b3717d74875，
release image571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a，source
f13155ed63a3137d41766ee587d9b4b96a81477f，过2026-10-27T03:44:30Z继续拒绝，不改有效期。

唯一待落地收件路径：
`/home/admin/ISSUE76_STAGE_A_94326ff1f3eb.zip`。
本窗口**没有UK上传/执行工具**；已连接状态/OS结果只读工具不提供文件上传/任意Shell。
不把本地存在冒成服务器存在，不用过期signedURL、不从服务器临时下载公网包。

根审及Owner具体批准后，最少人工步骤仅：
1. 从本窗口取上列一个完整57.18MB包；保留固定文件名。
2. 用Owner**原有**UK admin SSH/SFTP客户端文件上传功能，仅上传一次到上述完整路径。
   不开新SSH/HTTP服务、不索新密钥、不换账户；目标已存在/上传中断/摘要不符时保留，不覆盖、
   不自动续传或改名绕过。若Owner现有会话只有无上传功能的控制台，或客户端不支持该大小，
   此项运输仍HOLD，需原连接负责人确认既有文件上传能力；本窗口未现场验证SFTP已可用。
3. Owner原admin交互会话运行根审后的完整 `stage-a-owner-call.sh` 文本一次。命令没有PHASE、
   PERMIT_SHA、包URL或占位值；完整文件已随本候选交出，不要求Owner下载拼接Python。

本轮不要求Owner操作，上述是未来根审后的输入交付范围。没有自动云运输/接收登记能力就
如实缺失；手工SFTP不能冒充长期云接线通道验收。

## 2 完整原调用链与真实批准来源

完整外层固定文件为 deploy/community-preview/stage-a-owner-call.sh：5076B，SHA256
 84b97a7c88144b5fc3e54ea481d92fa30fd0a560c18654468591fac6a864bfd8。
实际Python入口stage-a-entry.py SHA94326ff1f3eb5a3d71cdd0cd7ab1846e0beca3dc5e11d4be34c9cc8d2d000f65。
完整链：原admin终端→条件子shell→sudo -n原Python隔离模式-c固定正文（stdin/stdout直接继承终端）→只读收件包→全包/六成员/manifest/
四输入SHA和路径保护→加载已核新阶段A源码→原root BASE锁→受控sudo操作确认行→原保护许可
记录→**原prepare-site.sh→原site_prepare.main**→原install/image_load→结果与许可归档。
原core/b789/产品算法无改动，没有新的部署通道、服务或权限scope。

### 批准与servertrust分开

代码只接受原UK/root、既有admin的SUDO_USER/UID/GID与原OS pwd一致、内核本进程loginuid
为该实际admin UID（非unset/root/未知），以及该进程的本进程的controlling TTY（首次可为后台组）。
两个阶段各在/dev/tty显示**实际输入manifest所绑定scopeSHA**，消费相应阶段的精确确认行
`APPROVE_INSTALL ae9f71cce106bd0e39f838659728c45f5fa75f1eb82645230cba98b46e7b8e74`，
随后`APPROVE_IMAGE_LOAD ae9f71cce106bd0e39f838659728c45f5fa75f1eb82645230cba98b46e7b8e74`。
这两句仅为未来运行时终端逐阶段确认内容，不是当前批准，不需Owner替换命令变量。

这是Owner本人沿原sudo权限的实际操作记录，不是机器签名/独立approve/servertrust；源码
明确servertrust=false。它不能辨别共享admin背后的自然人，因此仅适用于Owner本人原受控
终端；不能把转贴聊天、“approved=true”、脚本入参或runner模拟TTY当成Owner批准。
若要求自动化或独立签名Owner身份，当前没有已证映射，仍需原受信接线，不由此适配补造。
无原sudo上下文、内核loginuid未设/不符、无本进程controlling TTY、拒绝/超时均在写许可前HOLD。
根审通过本源码也**不等于**Owner已批准现场A。

### 两个单独许可与无重试

每阶段消费对应确认行时取服务器issued_at（不是该行的物理输入时刻），固定expires_at=issued_at+600；不在耗时后重新取最新时间
延长该次许可。A两个evidence字段始终null；许可canonical编码、root0600，写前/写中/同步前
重核同一操作上下文与期限。完整输入复制和读回耗时跨期时零对应许可/调用。

install成功且结果精确匹配原caller后，保存stage-a-install-result.json，将本次确切许可
复制归档为site-prepare-approval.install.json并复核后退役本次活动PERMIT；仅此后才询问
image-load真实新阶段确认并写新的≤600秒单许可。image-load结果核对后同样保存与归档。
现有/未知活动PERMIT、ENTRY、INSTALL、journal或attempt/阶段结果/归档任一存在即HOLD。
已有INPUT只有完整四输入、root0700/0600且摘要全部匹配才可复用；额外文件/部分执行拒绝。
不自动修复、刷新过期许可、覆盖冲突记录、重试load、从失败阶段自动接着执行。

## 3 精确读写与动作边界

只读：固定/home/admin收件包（root或原admin拥有、普通单链接、无组/其他可写、父链nofollow）、
OS admin UID/GID、本进程内核loginuid、/dev/tty、原BASE及固定目标的metadata/公开字节；
原image-load所需Docker固定image窄inspect、DockerRootDir/overlay2固定metadata容量投影。
不读config/DB/客户正文/Env/secret，不扫描未知根目录、不HTTP探活/刷新current。

批准后最多持久写：
- /opt/xuanjun-community-preview/image-f131-40059478387：新root0700（已有完整精确公开输入可复用）；
  四输入各root0600。原image-load还可写单个内层tar、load intent、observed三个原文件。
- 原site-prepare-v1.py、原control-oci2330-v1载体八文件及子目录、空update-journal父：原caller
  已审语义，文件root0600/目录root0700，不补建/覆盖原BASE，不触碰旧rollbacks。
- BASE/stage-a-attempt.json、stage-a-install-result.json、stage-a-image-load-result.json，
  活动site-prepare-approval.json（分阶段各一次，阶段完成精确归档后退役自身记录）、
  site-prepare-approval.install.json、site-prepare-approval.image-load.json：root0600。
  attempt明确MANUAL_SUDO_ACTION_RECORD_NOT_SERVERTRUST；没有独立签发声明。

Docker动作最多原固定f131一次image load；已精确加载复用。无pull/build/tag/任何容器run、
stop/start/rename，无安装service，无业务更新或private backup。原image-load inspect未知
不作不存在；原intent后未知不再load。现服务/旧回滚/账户/私有data/config/端口保持原状。

安装父阈值纠正为**192inode**（原space的64+保留128），不是文档旧写128。新预置四输入还
提前预留四输入字节+2×内层tar+2×载体+1GiB、192inode；复制前再取容量并核原确认未跨期。
原caller之后仍独立核它已审的INPUT及daemon容量门禁；这不是已观察现场空闲值。

## 4 异常收尾、完整外层与测试范围

外层仍在条件子shell里运行sudo，不退出父登录shell、不改父errexit。**sudo不在$()、管道、
heredoc或stdin/stdout重定向中**；完整固定Python正文用shell引用后作为-c参数，原stdin/stdout
直接继承Owner终端。Python仅在自身内部暂存固定entry的Python print结果，/dev/tty的实际
os.write/select/read不受影响，底层fd0/1仍为终端。

验收必须同时看到两条独立记录：
1. Python内部严格校验原完成JSON（固定image、四个精确False布尔字段、result为int0，重复key拒绝），
   打印state=STAGE_A_RECEIPT_VALID_NOT_UPDATE、stage_a_result_valid=true、child_exit=0及原completion。
2. shell紧邻sudo返回保存真实$?，独立printf record=SUDO_CHILD_EXIT、child_exit及login_shell_preserved、
   shell_exit_not_acceptance、servertrust=false。该值必须为0且与第一条一致。
任一缺损、不一致、非0/信号码/空结果/HOLD/异常均不得验收；外层不推断已完成。顶层shell rc0
只表示防退出控制块返回，**绝不表示A通过**。若sudo本身拒绝/被信号终止，可能没有第一条记录，
仍打印原childcode，保留父登录shell，不拿该shell状态冒PASS。
root适配始终finally释放固定BASE独占锁、TTY和FD；原子写的部分文件、活动许可/intent、
阶段结果保留供根查，不rmtree/unlink未知历史。仅完成阶段自己的确切活动许可可退役；
归档冲突先HOLD不覆盖。新增适配进程通过PIPE单独限制stdout16KiB，使用原3b6 child_status/finish_child作有界原组清理；阶段install的regular-file RLIMIT_FSIZE固定131072B、image-load固定67108864B，继承hard低于需要则拒绝，不设无限额；原caller文件/其子进程16KiB policy保持原字节。外层bootstrap最多300秒；原load本身
120秒；CLI cleanup不证明daemon操作已取消。非0、格式/版本不符、跨期、异常或清理未知
均停止，不推进下一阶段；所有自持FD即使一项close失败也继续逐项释放，清理未知不返回成功；归档退役前绑定本次活动许可inode/metadata，替换则HOLD保留；外层仍恢复，原44项安全语义直接复用。

本轮28项适用联验（保留a89已过范围，替换不充分的直接read测试并补生产confirm调用形态）：完整适配→真实shell→独立bootstrap Python中的原wrapper精确AST→exec独立caller Python→原main/install/import primitive，
真实保护临时文件/许可/归档/锁与私有模式；Root/Owner/TTY、所有Docker及image外层字节
入口为明确合成fixture。原caller/wrapper函数主体不改，仅测试root路径/UID/exec边界投影。
另核完整单包校验器对SHA篡改/symlink拒绝、外层真实bash+errexit仍活、无确认零写、输入
复制/第二阶段跨期、install/image异常、归档冲突、原kernel loginuid未知拒绝。
未运行真实sudo/Docker/UK，没有把这些结果叫现场验收；原镜像hash/算法44项复用不重跑。

## 5 剩余一次列齐

根独审此新完整候选；Owner精确A现场授权；一次57.18MB原路径输入上传及真实摘要回执；
原admin sudo/内核loginuid/前台TTY能力、固定路径不存在或纯输入精确可复用、实际容量。
目前没有任一UK落地证明或许可记录。本窗口的正常GitHub读/制品获取不能替代UK上传。
若上述原权限/身份/运输能力缺失，HOLD并报准确项，不新密钥/服务/权限、不模拟servertrust。
B/C、私有备份、真实更新、旧2330 backend时间及生产OCR权限均不由A解除。


## 6 8028完整独审四项修复与仍未知

8028原18项/bash-n与四输入重算复用；8028旧包57177136B/0b1dbd4e31fe55de1be29c7a140fea155a05b9178f6a1681c721029cc97e0754
只作历史，不是当前新适配包。新单包/入口摘要见本页与stage-a-delivery.json，原四输入字节完全不变。

真实子进程正例执行原wrapper bootstrap写完整32470B入口、exec原caller；新适配install上限
128KiB满足它，image阶段64MiB满足原57365044B合法tar。负例真实继承16KiB时入口恰被截为
16384B、caller未执行即HOLD，部分文件保留。原caller子进程的原16KiB RLIMIT实际探针仍为
[16384,16384]；新适配stdout PIPE超过16KiB则HOLD，不用提高日志限额来修合法文件写入。

a89外壳用$()收集sudo stdout，配合sudo use_pty可能使命令初始后台且不转发TTY输入；
生产confirm的select先于read，不能据直接read的SIGTTIN正例宣称它能交接。该旧测试已替换：
真实私有PTY后台进程执行**原生产confirm**，无预注入/无人工job-control交接，实际select超时HOLD。
新正例运行生成外壳→argv/FD直通sudo fixture→隔离Python→原生产confirm/select/read/gate/close，
等待每次实际提示后才发送精确确认行，两阶段均完成，底层stdin/stdout必须是真TTY。没有测试驱动
预先排队输入或tcsetpgrp/发SIGCONT让正例通过；也不新造生产job-control机制。
同一实际调用形态实测EOF、错误确认、真实select短超时、select异常、清理异常和确认过期均HOLD，
TTY关闭、Python记录与sudo childcode一致且父shell继续。Python完成校验另覆盖错返回码/bool、
重复JSON、空值和非bool伪False；外层覆盖0/2/17/143退出值，0本身不冒完成。
UID/Owner/时钟、短超时、sudo直通、局部合成成功结果为明确fixture；无实际sudo、UK或Docker操作。
UK实际use_pty、策略、终端传递能力仍UNKNOWN，须未来另获具体批准后验，未以本地PTY冒现场。
生产不改use_pty/sudoers，不主动tcsetpgrp/发SIGTTIN，不改安全设置。
两确认行可以在第一提示之前预排队；第二次读取成功不能证明第二行一定在提示后输入。
两段许可的时间是该阶段消费确认行的服务器时间，不是独立Owner身份认证/签名/机器授权，
不能用这个操作记录替代外部的Owner精确现场批准。所有servertrust字段继续false。
本进程仅选择读取SUDO_USER/SUDO_UID/SUDO_GID非秘密元数据，不读取应用/容器Env或secret。

本轮把site-preparation-manifest里的workflow/governance等每个列出文件的真实bytes/SHA全部
重新核对，并登记当前新适配/完整命令/文档对象；不把旧字节标当前同版。完整输入包、manifest、
源码、调用块及CI制品分别核摘要；包外层digest不代替任何内层digest或Git blob匹配。

## 7 a89 TTY单项收口的版本边界

a89原24项及根独立/外层审计通过部分复用；本轮只更改builder生成的新外壳和测试/交付证据。
管理入口stage-a-entry.py与四个输入完全不变，因此完整57179504B包及其258ce847完整SHA仍相同，
不是新产品镜像；必须配本页新5076B外壳，不能继续运行a89旧4865B命令。
3b6原caller/core/f131没有源码改动或重建。现场状态仍NOT_EXECUTED，根本次独审仍PENDING。
