# 原阶段A完整交付候选（仅送根审，现场NOT_EXECUTED）

原3b6be4aa1ff06d088fe26f44f08b9a505c5b5513 / Tree cdd9ae50d91d65cebac79897a414ff4d9a6032ec
两修44项及独审SCOPE_PASS直接复用。原caller/wrapper字节、b789/core、111330B载体及f131
镜像均不变；本轮只增加固定阶段A适配、离线打包、防外层退出入口及新联验。

## 1 一包四输入与固定目的地

本地已实际生成单包 `ISSUE76_STAGE_A_9b071542577c.zip`，57177136B，SHA256
0b1dbd4e31fe55de1be29c7a140fea155a05b9178f6a1681c721029cc97e0754。
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
`/home/admin/ISSUE76_STAGE_A_9b071542577c.zip`。
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

完整外层固定文件为 deploy/community-preview/stage-a-owner-call.sh：3569B，SHA256
 0d89a73d36229cc375cd02bad09b824d1baa04e416f4bc8cc19c5ac5f5b70656。
实际Python入口stage-a-entry.py SHA9b071542577c6ddd932826a167dbbd262c2f8493c093c147d475915c5aa7a727。
完整链：原admin终端→条件子shell→sudo -n原Python隔离模式→只读收件包→全包/六成员/manifest/
四输入SHA和路径保护→加载已核新阶段A源码→原root BASE锁→真实Owner阶段确认→原保护许可
记录→**原prepare-site.sh→原site_prepare.main**→原install/image_load→结果与许可归档。
原core/b789/产品算法无改动，没有新的部署通道、服务或权限scope。

### 批准与servertrust分开

代码只接受原UK/root、既有admin的SUDO_USER/UID/GID与原OS pwd一致、内核本进程loginuid
为该实际admin UID（非unset/root/未知），以及该进程的真实前台controlling TTY。
两个阶段各在/dev/tty显示**实际输入manifest所绑定scopeSHA**，要求Owner本人当场精确确认
`APPROVE_INSTALL 4d77302682886cc9469a906c59e09c1972dc3eeed1b0b2f8cd65f65affc7a279`，
随后`APPROVE_IMAGE_LOAD 4d77302682886cc9469a906c59e09c1972dc3eeed1b0b2f8cd65f65affc7a279`。
这两句仅为未来运行时终端逐阶段确认内容，不是当前批准，不需Owner替换命令变量。

这是Owner本人沿原sudo权限的实际操作记录，不是机器签名/独立approve/servertrust；源码
明确servertrust=false。它不能辨别共享admin背后的自然人，因此仅适用于Owner本人原受控
终端；不能把转贴聊天、“approved=true”、脚本入参或runner模拟TTY当成Owner批准。
若要求自动化或独立签名Owner身份，当前没有已证映射，仍需原受信接线，不由此适配补造。
无原sudo上下文、内核loginuid未设/不符、无真实前台TTY、拒绝/超时均在写许可前HOLD。
根审通过本源码也**不等于**Owner已批准现场A。

### 两个单独许可与无重试

每阶段批准时取真实issued_at，固定expires_at=issued_at+600；不在耗时后重新取最新时间
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

外层`if ( set +e; sudo ...; 记录inner; exit inner ); then ... else ... fi`把exit限制在子shell。
父登录shell无exit/exec、无set -e变更；即使父已有errexit，inner失败仍记录内外码并回到父。
没有把失败exit强改成功；打印LOGIN_SHELL_PRESERVED表示父仍存活，不表示A成功。

root适配始终finally释放固定BASE独占锁、TTY和FD；原子写的部分文件、活动许可/intent、
阶段结果保留供根查，不rmtree/unlink未知历史。仅完成阶段自己的确切活动许可可退役；
归档冲突先HOLD不覆盖。原caller进程沿原3b6 capture限300秒+原有界group清理；原load本身
120秒；CLI cleanup不证明daemon操作已取消。非0、格式/版本不符、跨期、异常或清理未知
均停止，不推进下一阶段；所有自持FD即使一项close失败也继续逐项释放，清理未知不返回成功；归档退役前绑定本次活动许可inode/metadata，替换则HOLD保留；外层仍恢复，原44项安全语义直接复用。

新增18项隔离联验：完整适配→原wrapper精确Python AST→原main→原install与import primitive，
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
