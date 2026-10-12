# Issue19 代码审查与回执后续接门禁

本变更沿PR17父任务和Issue19；纯数据函数，不建立队列、不取得英国writer、不修改P2安装分支、不更改lease/fence、不执行提交代码。

`review_bundle` 对WORK/CHATGPT/DOTS同等处理：合同绑定task/spec/checkpoint/目标仓库/base/code commit及逐文件SHA256；只接受明确白名单路径、限定大小的UTF8 LF字节。Python AST及JSON只做语法检查，不执行内容。其他格式保持HOLD，由受限外部检查器处理，不能将bash语法通过作为安全审核。

独立QA和Security必须使用两个不同且经验证的审查身份，禁止开发者自批。两者均绑定完全相同bundle摘要，改字节/commit/合同后旧审核失效。调用方必须从认证来源取得合同和审查回执；不能把提交者自带的review JSON当成真实批准。通过只允许进入隔离测试，永不授予发布批准。额度归属及零Codex路径由外部独立审计，不由来源标识证明。

`continuation_due` 在读取回执后根据canonical证据检查：真实执行、接收确认的交接、具体HOLD三种闭合；读回执、心跳、仅提交handoff都不算闭合。5/10/15分钟分别返回补收件、核对并恢复同attempt、缺续接HOLD；不杀进程、不夺权。持久化和真实唤醒须接入原canonical ledger与已验证runtime，并按每个执行者实测。本函数不是部署后的全员监督服务。

## 机械语法门禁优先执行

Owner16:30澄清：聊天/Dots生成代码后，首先自动拦截符号和语法错误，提高执行效率，不应等待模型审查才能进行语法检查。

`native_syntax_gate` 支持Python编译但不执行、Shell `bash -n`、JavaScript `node --check`、JSON严格解析和固定TypeScript编译器的语法诊断。拒绝破损引号/括号/缩进、非法UTF8/CR/NUL、重复JSON键、超量输入；缺编译器或格式未支持明确HOLD。语法通过不能证明逻辑、命令安全或类型正确；独立审核在后续执行准入阶段保留。

现有`CODE_READY`收件路径接入`native_syntax_intake`：从明确base/head提交读取受限GitHub blob，验证祖先关系、完整tree、普通文件mode、blob SHA及大小；不checkout、不运行上传代码。仅支持当前获准控制仓库，其他目标仓库待任务授权后扩展；不借消息扩大白名单。语法结果绑定task/spec/checkpoint/入口/base/code commit和文件SHA256，错误回执不包含源代码或解析器原始stderr。修改后按新commit重新检查，不复用旧PASS。

状态为`PASS_SYNTAX_NOT_ADMITTED`或`HOLD_SYNTAX_GATE`，均不授予writer/主机权限。检查脚本需独立审查后合入main才会成为实际收件门禁；分支CI证明测试终态，不证明已上线。本PR仍不解锁P2安装。
