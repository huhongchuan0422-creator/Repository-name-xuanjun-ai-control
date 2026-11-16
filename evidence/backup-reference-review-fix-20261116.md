# 86101e02 备份回执引用修复（作者自测）

基线commit `86101e02b7247d79c4fba4412f54dd80b8f1be26`、tree `ffe7ea832aac5911f8ab29ac71043f8edef5559d`；原tracked无改动，保留上轮本地未跟踪测试日志及缓存，未reset/覆盖。原TC共享树13项dirty不动。原作者/独审接续由main协调，本会话无官方会话状态工具，无法独立证明所有相关会话停止或全域无未知effects；本次仅在原隔离候选执行，无网络/远端/生产写。

独审发现base_ref/result_ref只经过ident而绕过safe；合成敏感形态可出现在UNVERIFIED_REPORT中。本次仅改变这两字段的值类型规则：纯十六进制裸值必须是小写完整40位Git SHA-1或64位SHA-256，不接受短前缀、异常长度或大写；其他结构化引用（包括UNKNOWN）仍经过既有safe，不因是base/result跳过。仅保证格式，不证明该hash来自源码、已授权、无秘密或经过脱敏；真实来源仍需原服务/保管方校验，不能把秘密hash当脱敏。已有固定exclusion分类仍沿用原逻辑，非固定引用仍受safe。

`PYTHONPATH=scripts:tests python3 -m unittest -v test_backup_reference_delta` 4/4：base/result各合成sentinel拒绝，合法完整版本hash及安全别名、UNKNOWN/错误类型/短前缀、固定排除分类和额外敏感形态；`PYTHONPATH=scripts:tests python3 -m unittest -v test_backup_receipt_delta` 5/5（含默认UNAVAILABLE、无变化不产生备份、固定排除、原只读路由）；compileall OK。日志分别在本目录 `backup-reference-delta-tests.log`、`backup-reference-mapper-regression.log` 和 `backup-reference-compile.log`，不纳入代码归档。未重做原354四事件或旧归档恢复；复用独审已过范围。敏感sentinel仅合成，测试输出不包含其值。

五分钟仍为目标而非已启用：目的地/纳管待Owner决定，未接provider/可信回执、timer/config/网络或认证。`map_report`仍仅UNVERIFIED_REPORT，不升级来源或权限。原354接件、Writer、运行、三方监督仍UNKNOWN，未改原受保护资料。作者不自审，交同一非作者仅复核本delta。
