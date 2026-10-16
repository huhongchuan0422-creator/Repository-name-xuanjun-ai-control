# PR122 国内客户中心固定 root 通道

## 1. 范围

Owner 已在国内 root 终端待命。现有 Runner 为 githubrunner UID1002，无无密码 sudo。此增量复用原 PR122 与客户中心发布器；不修改或重新构建已审核 feaef687 客户包，不授权 DNS、东京、P2、Finance、Binance 或任意 root shell。

## 2. 固定能力

Owner 在通道自身完成独审后，以准确源码 SHA256 核实下载脚本，亲自在 root 终端调用 --grant。安装前固定输入 /root/PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz 必须是获审客户包，TAR=7dd77ef573c338201ddc886b23585422ad4a07ae563a9c6ff92fe5b2f9d97b98，Manifest=570bb453bb13b372a9fed1900ec37594be979be3e423c14955db539ae7056b89。全部34成员、33文件先检查，再写入 root 私有 /var/lib/xuanjun-customer-channel。脚本不从 GitHub 评论自行认定独审许可；人工 grant 命令仅在独审通过后交付，不把源码作者自报角色当批准。

sudoers 仅允许 githubrunner 执行 /usr/local/libexec/xuanjun-customer-channel 的 inspect、plan、apply、rollback 四个准确参数。无通配、任意路径、可变命令或 shell。封闭环境保留 sudo 生成的 SUDO_UID，拒绝其他来源；所有目录链 root 持有且组/其他不可写，拒绝软/硬链接及文件变化。--grant 和 --revoke 不在 Runner 允许列表。

inspect 仅输出固定配置的存在与 owner/mode，绝不读取正文。plan/apply/rollback 每次完整核验冻结 bundle 及 TAR，再导入原发布器；不导入仓库 checkout。互斥锁阻止并发发布动作。apply 的唯一批准 ID 来自 Owner root0600 /etc/xuanjun-customer-center/CHANNEL_ACTION.json，严格为 {"action":"apply","approval_comment_id":真实整数}；原发布器仍校验独审签名、root信任、真实评论锚、CI/制品、现场证据与单次事务。没有真实许可不得填写占位批准。

安装不创建客户运行账号、不安装依赖、不生成密钥、不登记审核信任、不填充渠道凭据，也不调用 apply。该通道解决受控调用权限，不能代替这些真实业务前置。当前所有生产前置仍 HOLD。运行时正常输出仅允许 state/transaction/manifest/source/production_changes，异常正文不输出到 Actions。

## 3. 异常与撤销

grant 使用排他创建；已有 BASE/EXEC/POLICY 拒绝覆盖。PREPARING 在任何中断后保留，禁止直接重跑。真实 visudo 先验证全局和候选，再安装规则并验证全局，最终才标 GRANTED；部分阶段失败时 dispatcher 不运行。Owner 保留所有现场证据，核查后处理。

Owner 在 root 终端手动 --revoke 只删除与本通道准确内容一致的 sudoers，检查全局语法，保留代码、冻结包和回执；不停止已在执行的动作、不回滚客户数据或服务。正在执行的动作先核实终态，不能把撤销规则等同中止事务。

## 4. 验收与边界

初版0575b4c1的Hosted Job虽然SUCCESS，但原始日志实际为17项中1项ERROR（全局visudo -c）；不得引用为17/17。最小修订只调整测试与CI：测试使用真实visudo检查临时完整sudoers及include树，避免依赖Hosted全局策略；另以故意损坏的临时sudoers验证真实非零拒绝。生产脚本仍校验实际全局sudoers，未放宽。工作流显式set -euo pipefail，并实测false管道返回失败；同时要求日志包含Ran 17与单独OK行。旧错误记录保留，最终必须引用新准确CI。

tests/test_pr122_domestic_customer_channel.py 为 root 临时夹具，真实 visudo 与冻结客户归档校验；只在临时 root 目录写夹具，不写实际 sudoers。Hosted 证据不是国内安装证据。准确 CI、通道制品哈希、独审结论及 Owner 执行回执取得前，不提供生产 --grant 命令、不声称授权已落地。后续角色/依赖/配置准备若需要新的特权动作，必须明确注册审核，不能用此通道偷偷扩展。
