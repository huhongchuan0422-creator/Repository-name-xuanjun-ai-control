# Phase-C 韩国元数据补充（2026-10-16）

原PR99源码不变，Phase-B独立6209166651验收继承。原PR99准备设计最新提交7b49512d272cc4f77e223cd0130464d83e036624；完整C适配实现/制品仍未完成，不是送执行审状态。

原PR122分支71f9e115触发既有v27-readonly-batch队列一次，只运行Korea非root元数据Job116839560203（Run38859895705/SUCCESS），其他所有主机job均skipped，没有checkout/sudo/凭据/DB/provider请求/服务动作。source f027131c4c0a7f25a7c85b8d46c20f43ed182bb0ca32adef232ed48526632576，原始日志receipt已归档。

实际UID1001，候选UID/GID986/nologin，systemd239/Python3.11.13/cgroup v1 memory controller，nft1.0.4、OpenSSL1.1.1k；候选inactive/dead/PID0、PrivateNetwork=yes、RestrictAddressFamilies=[unprintable]（不重做既有typed-D-Bus独审）。据此准备独立nft inet/meta skuid候选，不能将软件存在视为root enforcement PASS。

v1的iptables/ip6tables --version通过resolve后直接调用xtables-nft-multi，丢失argv0别名，exit1因此标UNKNOWN，不能推断不可用；v2保留绝对调用别名，已在本地真实symlink/multicall回归通过，未在韩国重跑。旧日志/v1来源不改，避免为非关键版本字段重跑整批。v2文件单独保存，workflow仍锁原v1 hash，不能混报已执行v2。

接下来集中实现真实网络围栏、readonly custody、WAL发布/独立verifier及持续窗口接线，再一次送完整候选审查；不为模型分数分批重审B。root前检、服务启动后隔离、真实GET、持续Shadow均未授权未运行。网站/Work/current/DNS、东京服务和共享业务不改。Owner当前无需操作。
