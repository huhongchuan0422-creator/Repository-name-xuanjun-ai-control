# PR122 固定字节只读 Plan 入口

本增量关闭#6227148327的P1_EXACT_INPUT_PIN源码缺口，不修改已经独审通过的bc940421运行包，不重建业务页面。当前尚未获国内执行许可，本文不要求Owner立即运行。

## 固定输入

- 主机：iZvt5t8tlrm8oiZ；只能Owner root，拒绝SUDO_UID=1002。
- 使用系统Python的-I -B模式，拒绝非隔离/允许写字节码模式。
- 输入目录：/root/pr122-customer-channel-upgrade-inputs/。
- REVIEW_ARTIFACT.zip必须为原Artifact12082187996原始ZIP，SHA256=d03a09d3110cf372d5c6209da4514fffd77f8487c6a36532744e80557ac353d8。
- approved-upgrade.py必须为原包内升级器，SHA256=9edc15851d653cdbc9366ebc7dcdd8215b2df3814248065fe96d704acbf1111c。
- 原受保护通道目录固定/var/lib/xuanjun-customer-channel，不允许参数替换。
- guard.py自身准确SHA须由后续独立许可绑定，Owner启动前复算；源码存在不等于执行批准。

## 只读执行顺序

1. 验证主机/身份/解释器模式。所有输入及父目录须Root所有、非链接、不可被group/other写入，输入为单链接普通文件；限定大小。
2. 完整读取并复算原ZIP及升级器准确SHA。任何内部自洽但外层ZIP不同的替代包均拒绝，错误输入在执行升级器定义前停止。
3. 从同一份已验证源码字节加载标准库函数定义，不运行__main__，不导入客户候选；固定ZIP以内存中的准确字节供原bundle读取。
4. 原plan完整核验Root GRANTED、旧34文件候选、原代码/包、wrapper/sudoers及权限。连续读取两次完整Plan并比较；复核冻结新代码/源提交，最后再验证磁盘输入SHA。
5. 仅输出原完整Plan、规范Plan SHA及输入身份，production_mutations=0。不创建事务目录或锁文件，不改变GRANTED、sudoers、账户、软件包、凭据、unit、Nginx/current或DNS。

CLI仅有plan，不提供apply、rollback、任意输入路径或新sudo动作。后续安装必须另行取得准确计划许可。原GRANTED/旧目录现场状态仍UNKNOWN；源码测试不能替代Owner现场只读结果。

## 测试和制品

本地/Hosted单测使用Root私有临时合成fixture，固定生产常量只在测试进程中patch，不影响交付源码。覆盖正确输入不写文件、错误ZIP/源码、link/mode、身份/主机/解释器、禁止动作及两次Plan漂移。Hosted另下载原Artifact的真实原ZIP，验证原ZIP/TAR及升级器固定摘要，生成包含原ZIP原字节、guard、原升级器、测试/工作流及本说明的独立审核包。原业务运行包不变，不重复129项业务回归。

Root运行环境、扫描器/病毒库、私有配置/信任、真实合同映射及六Unit生产安装仍为独立未完成项，本入口不绕过它们，不签发生产许可。
