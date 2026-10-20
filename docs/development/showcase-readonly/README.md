# 国内 showcase 固定两文件只读候选

任务 PR122 #6290758973；接单 #6290788952。基线 a204163292806fb259013ea802c4363fd2fc3578。只准备源码与合成测试，不操作国内或其他服务器。

## 完整候选

同目录 CANDIDATE.sh 为完整自包含 sudo/Python heredoc，无占位符、下载、临时文件或远程依赖。候选SHA256：96c36a9c71b18bfbd02778c719d7c6381b5c540137ed412305bf658af7471436。
源码 scripts/pr122_showcase_readonly.py SHA256：8a87035a1f03060b7a8af235a40bb824edee9292c5d9e51bff7eb9cec2fa32b5。
现场执行须Owner另确认，本轮 NOT_EXECUTED。

固定主机 iZvt5t8tlrm8oiZ，真实/有效UID0。仅打开 /、/etc、/etc/xuanjun-showcase 及：
- /etc/xuanjun-showcase/INDEPENDENT_REVIEW_TRUST.json
- /etc/xuanjun-showcase/BUILDER_POLICY.json

不枚举目录、不读取其他配置/凭据，不调用builder/plan、服务、账户或安装器。没有可配置路径、环境覆盖、网络或子进程。默认只输出stdout，不自动保存回执或日志。

## 复用与读取边界

继承原 scripts/pr122_account_admission/readonly_probe.py 的 identity：只读FD、完整流式SHA、FD/命名路径前后dev/ino/size/mtime/ctime核对；继承原 showcase_trust.load / protected_build.private_bytes 的root私有0600、单硬链接、普通文件和祖先保护规则。没有加载原生产模块，因为其依赖并非自包含且不需要调用授权/构建。将相同读取模式嵌入诊断候选，并为本次逐组件dir_fd/NOFOLLOW要求增加祖先FD绑定与回查；不改变原生产组件。

祖先必须root:root且不可组/其他写；叶文件须root:root/0600、普通、单链接。保护不符只给已观察metadata与UNKNOWN原因，不读正文或计算SHA。每文件<=1000000字节；65536字节流块；JSON深度12、字段总数12000、单对象字段1000、单数组1000、节点20000、字符串4096、整数20字符；拒绝重复key/浮点/非有限数。只读操作总alarm15秒；stdout<=16384 UTF8字节。拒绝符号链接/FIFO/设备等，不打开特殊文件。

ENOENT需先复核已打开祖先及再次核缺失组件，才报告ABSENT_AT_OBSERVATION；缺父目录时输出missing_component，不伪称文件被实际打开核过。EACCES/EPERM为ACCESS_DENIED；类型、权限保护、读取变化、替换、超限、JSON或IO异常为UNKNOWN。不能把未知当不存在。读取中变化清除sha256和selected，不给不稳定摘要。

## 非秘密字段

共同输出：准确目标、存在性/观察状态、大小、UID/GID、mode/nlink/type、祖先保护metadata；稳定受保护普通文件才输出SHA256。registration始终UNKNOWN，摘要和配置声明不是独立登记证明。

trust仅选择：schema、source_writer_principal、固定CONTENT评论6214465866对应anchor的reviewer_principal/custody和body摘要/scope/issued/expires、目标撤销标志、对应reviewer状态及custody摘要相等性、writer/reviewer字符串是否不同、既有CONTENT摘要绑定与观察时刻有效期分类。principal仅允许128字符内的标识符字符。外部custody来源真实性、独立性始终UNKNOWN_NOT_ATTESTED。其他anchor/reviewer记录不打印；未知顶层schema/字段不输出selected，不打印原文或异常正文。已知CONTENT正文/源码/schema无需重新交付。

policy仅选择schema、mechanism_manifest_sha256、shell_tar_sha256、legacy_pages_sha256及reviewer_logins数量/规范JSON列表SHA；不打印login列表或其他字段。

## 副作用、失败与恢复

没有内容/属主/权限写入，无锁文件、临时文件、安装或服务动作。sudo/系统审计可能写日志，普通读取可能更新atime；不称零系统写入。Owner若手动重定向输出会自行新增回执文件，不属于默认候选行为。

任何异常保留原现场，候选没有清理/回滚/重试代码；输出QUERY_INCOMPLETE时该次观察不足，不能拿之前局部结果当成功。若SSH断开且stdout未保存，结果UNKNOWN；本次不隐藏增加日志文件。恢复须先保留原回传、确定错误，另按确认范围重新只读观察，不新建或修补信任文件。

## 验证与环境

原既有国内回执 PR122 #6213028183 曾观察/usr/bin/python3=3.11.6；该历史值不是当前实测。候选为stdlib Python>=3.6语法，运行时报告实际版本；不升级解释器。实际国内宿主执行NOT_EXECUTED；实际Python3.6解释器NOT_EXECUTED，语法检查不冒充解释器验收。

21项合成测试：固定main两路径/输出上限、保护属性、缺父/缺叶、权限拒绝、链接/硬链接/FIFO/目录拒绝、文件和祖先替换、原件不变、脱敏未知字段、仅选目标anchor、policy摘要、严格schema/类型、撤销/失效/错误绑定、JSON/字节限额、超时/IO及完整命令嵌入一致。首次本地测试有1项期望PATH_CHANGED但重命名先改变原inode ctime而正确报FILE_CHANGED；修正该测试的精确阶段，并另加真正祖先替换用例，产品安全条件未放宽。最终本地21/21 PASS。Hosted终态由原PR122交付回执记录，未变旧组件不重测。
