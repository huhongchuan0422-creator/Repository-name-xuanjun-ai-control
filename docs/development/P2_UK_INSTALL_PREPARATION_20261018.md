# P2 英国安装集中准备与一次许可范围（2026-10-18）

本文件接续原任务PR17、独审PR58；是现场准备候选，不是许可、安装命令或生产验收。Owner要求连续推进，未变源码不重新开发、不重跑951项CI、不重复审核。
全项目规则引用：PR17#6248822639；原开发规范文档提交217022eafee8f492b8b6549124c5d8115b0429f0。其他窗口已经登记的规则引用直接继承，不再重复写入。

## 已核实与继承

- Source Commit f4f74fdd0b6aa49e046debabf81e438b17ff20b5；Tree 2c2e3c09cbda31df30e0d269b580348c55e6de87。
- Dots PR58#6248479254：PASS_SCOPE；双Python各951项，Run39116536913；本文件不变更上述源码或制品。
- 主候选Kit SHA256 da3c42f6dd6d030c337ffb358be0cbe77c64eb0912016ebf30a353f65451d83f；Manifest SHA256 41771b95c95b960cc643f06b1b3c622a880ed64a385d2f122322605b8abf106c；Artifact12132846727。Manifest声明production_ready=false、install_permit=NOT_ISSUED、release=HOLD，保留原字节，不伪改为生产已批准。
- D1完整终端回执26758字节，SHA256 9acfc34ee7001a6f25144faf50a9c8a552ea389b5552e925961776611f8b81e2；JSON17778字节，SHA256 be655983df50879449f62badb8577f4b5167ae38e15f4bfabad99db068d963b9；PR58#6248808149。私有路径与原始输出留在原受信通道，不公开。
- D1 CONSUMED / DIAGNOSTIC_RETURNED_HOLD；没有重跑。13个路径与3个目录结果复用；目录项95/32/70。UID/EUID0，Python3.6.8，数据库未打开、未请求写入。无独立退出码，不补造。
- 旧三件套、历史事务与备份的存在性证据保留；存在不等于可恢复、可重放或新版本授权。

## SQLite最小处理

HOLD_PARENT_PROTECTION是旧诊断要求父目录全部root属主且不可组/其他写而触发的程序保护拒绝；回执没有给出拒绝发生的具体父节点，不能认定数据库损坏、系统拒绝访问或应该改权限。
先以固定数据库路径逐组件只读核验实际uid/gid/mode、类型、设备/inode及前后稳定性，报告首个不满足策略节点；不跟随符号链接、不打开数据库内容、不递归枚举、不chmod/chown、不复制数据库、不移除WAL/SHM。
取得真实服务身份和父链后，决定采用已审核的身份绑定只读接口或一致性快照机制。禁止把弱化root父链条件当作已批代码修复；如需新适配器/源码，仅审该变化，不重开已通过主体。任何SQLite写入、迁移或切换必须另列入同一完整安装许可的准确范围。
现阶段：保护规则未改变；具体父节点UNKNOWN；生产目录修复NOT_EXECUTED。

## 新旧Kit安全并存候选

建议新根（尚未创建/批准）：/var/lib/xuanjun-p2-releases/f4f74fdd0b6aa49e046debabf81e438b17ff20b5。
其下archive/kit.tar.gz仅存原主Kit，kit/仅存严格Manifest清单；evidence/存下载与解包回执，绝不向kit/写日志、许可、Ledger或缓存。
建议持久控制根（尚未创建/批准）：/var/lib/xuanjun-p2-attempt5。Ledger与唯一共享AuthorityStore分区管理，准确最终路径待受信管理员确认；不能把旧业务state.sqlite推定为AuthorityStore。
下载只能来自上述已验证Artifact，先核验外层归档与Kit SHA，后核验Manifest及全部成员；拒绝绝对路径、..、链接、设备、重复成员及清单外项。只在新目录独占创建；目录或文件已存在即HOLD，O_EXCL及O_NOFOLLOW保护；部分输出保留并记录，不删后重试。旧冻结目录、旧Kit、原Prepare结果与事务文件均不修改。
正式入口是versioned_entry.imports加载核验后的PermitCycle + NativeRecovery可信组合；不是旧Delivery/Prepare命令。源码中的loader只核验/导入，不装配真实Provider、不签许可、不自行安装。不能直接给loader加任意main命令冒充生产入口。

## 唯一可信执行闭包：一次性缺项清单

| 必须由既有受信主机/服务通道提供 | 接收及验证条件 |
| --- | --- |
| 目标身份与唯一执行Writer | 当前真实host/actor/writer；各窗口与Runner在途状态；冲突即HOLD |
| Lease/Fence/Epoch | 签发者、当前generation/expiry、实际排他证据；旧锁文件元数据不能证明占用/空闲 |
| Issuer与认证通道 | 实际部署入口、服务身份、RSA公钥指纹与来源；不公开私钥/token；不得使用测试签名器 |
| 唯一共享AuthorityStore | 实际路径、权限、服务身份、历史保全/备份及无克隆/丢历史证明；禁止空库重建历史 |
| 原生事务与检查点 | Run/Job/InvokeId、outer/inner/phase回执、失败intent、备份checkpoint/log SHA与独立副作用读回 |
| 真实安装执行组合 | 已部署的host_readback/signer/transport及NativeRecovery factory/Driver/控制器绑定、准确入口文件及SHA |

源码IssuerService要求认证transport principal，而非JSON自报身份；host_readback必须给出准确事务ID、备份/检查点/日志SHA及结果。源码没有默认生产transport、signer、云调度或安装launcher。versioned_entry返回production_authorized=false。因此上述缺项不是重跑D1或重新跑CI能够解决。
本窗口现有可调用接口为GitHub/本地离线环境；未获得可直接操作英国主机的已连接SSH/RAM/Runner执行入口。历史Owner SSH可用不等于本窗口已有连接；不探测秘密、不借其他项目通道、不制造第二Writer。取得既有执行入口与上述事实后继续，不要求重新授予已存在的权限。

## 一份完整安装许可的集中范围

先补上述准确事实，再由Dots一次绑定：
1. 固定Source/Tree/Kit/Manifest及所有新执行胶水的准确版本、主机/执行身份、UTC有效窗、唯一Writer与服务端持久Grant；同一Grant最多5次，不逐次新批。
2. 上述独立新目录的下载、SHA校验、严格解包、最小目录前置准备；准确允许写入列表及拒绝覆盖/链接规则。
3. 原16阶段通过原生状态机、检查点和可信恢复完成；已成功阶段只核验、不重放，不SKIP，不重跑旧Prepare；明确107载荷等继承效应边界及原TLS限制。
4. 原许可明确列举的配置JSON目标、before/after/payload/checkpoint SHA；未批准调整拒绝。具体清单当前UNKNOWN，不授权任意配置修改。
5. 备份、一致性检查点、生产激活与有限失败恢复的准确对象、入口、预后置条件；不以“恢复”授权任意回滚/事务清除。
6. 失败自动诊断→可信对账→批准配置/恢复→幂等续接。签名/审计/回复或进程中断先从PermitCycle认证已提交结果收敛；原Attempt/ordinal/请求绑定保留，已关闭执行Fence不放宽。
7. UNKNOWN、部分写入未对账、Lease失效、Writer冲突先HOLD；可信安全恢复后同许可余额续接；成功停，5次失败停并集中报告；源码/范围变化停旧许可并集中增量审核后新许可。

## 当前终态与下一命令条件

OFFLINE_PREPARATION_PLAN=COMPLETE
UK_PREPARATION=PENDING_EXTERNAL_TRUSTED_FACTS
SOURCE_REVIEW=PASS_INHERITED
KIT_REVIEW=PASS_INHERITED
PRODUCTION_PROVIDER_BINDING=UNKNOWN
INSTALL_PERMIT_SIGNABLE=NO
INSTALLATION=NOT_EXECUTED
INSTALL_PERMIT=NOT_ISSUED
P2_RELEASE=HOLD

下一条真实安装命令尚不能安全定稿：缺实际可信执行入口、Provider/共享账本/事务绑定及正式许可。不得用猜测路径、占位参数、测试Provider或旧入口输出“可直接执行”的命令。
本文件将缺项及新执行范围集中记录于原PR17/PR58；只请求真实新增生产范围的集中处理，不提交未变951项源码重新审核。
