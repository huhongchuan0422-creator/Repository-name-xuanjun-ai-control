# Issue19 代码审查与回执后续接门禁

本变更沿PR17父任务和Issue19；纯数据函数，不建立队列、不取得英国writer、不修改P2安装分支、不更改lease/fence、不执行提交代码。

`review_bundle` 对WORK/CHATGPT/DOTS同等处理：合同绑定task/spec/checkpoint/目标仓库/base/code commit及逐文件SHA256；只接受明确白名单路径、限定大小的UTF8 LF字节。Python AST及JSON只做语法检查，不执行内容。其他格式保持HOLD，由受限外部检查器处理，不能将bash语法通过作为安全审核。

独立QA和Security必须使用两个不同且经验证的审查身份，禁止开发者自批。两者均绑定完全相同bundle摘要，改字节/commit/合同后旧审核失效。调用方必须从认证来源取得合同和审查回执；不能把提交者自带的review JSON当成真实批准。通过只允许进入隔离测试，永不授予发布批准。额度归属及零Codex路径由外部独立审计，不由来源标识证明。

`continuation_due` 在读取回执后根据canonical证据检查：真实执行、接收确认的交接、具体HOLD三种闭合；读回执、心跳、仅提交handoff都不算闭合。5/10/15分钟分别返回补收件、核对并恢复同attempt、缺续接HOLD；不杀进程、不夺权。持久化和真实唤醒须接入原canonical ledger与已验证runtime，并按每个执行者实测。本函数不是部署后的全员监督服务。

本轮验证：本地10项测试通过。独立审查、GitHub CI、英国runtime集成与全入口验收分别记录，不预填PASS。P2依旧需要真实认证消费绑定与精确安装计划；本PR不解锁安装。
