# 三入口统一接件与人工部署
2026年10月12日12:01（Asia/Shanghai）Owner变更：三入口立即接入；P2最终部署改为人工执行，不再等待自动root执行能力。

## 已实现接口与能力边界
Work、普通ChatGPT聊天、Dots使用同一个PR17接件协议和原任务，不建立任务数据库或平行队列。GitHub-hosted Runner验证消息格式并把机械收件回执写回同一PR；该工作流不调用模型、不运行提交代码、不授予writer或stop/handoff权限。
入口标识是来源声明，不能认证模型平台或证明额度独立。主机canonical ledger仍负责spec、checkpoint、仓库授权、lease/fence及停止交接对账。未通过主机门禁的消息状态为RECEIPT_VALIDATED_NOT_ADMITTED。
当前仅接入收件协议。Dots／普通聊天真实写入、事件唤醒、测试回执和停止交接均待各会话独立实测；不能用Work冒充。若该入口无法写GitHub，标记WRITE_UNAVAILABLE，保留断点。

## 原生入口接手指令
适用每个实际会话：打开权威PR17，读取最新任务、checkpoint、执行回执和#19，不从旧聊天重建任务。核验自己是否能够直接写入任务指定GitHub仓库。自己生成代码，提交指定分支；普通聊天和Dots禁止转交Work、Codex CLI或app-server。不能承诺后台执行或无限额度。
先确认原writer已停止及旧执行权已失效；无法取得canonical ledger确认就HOLD，不得并发修改。业务代码写task指定业务仓库；控制面代码才写控制仓库。测试由英国机械执行，回传精确commit/run/hash；取得终态后继续或明确交接。
下面是协议格式，不得把示例摘要作为真实摘要。entry为WORK／CHATGPT／DOTS；execution_path须分别为WORK_NATIVE／CHATGPT_NATIVE／DOTS_NATIVE。event为RECEIVED／CODE_READY／STOPPED／HANDOFF／HOLD。所有摘要必须来自原任务和真实提交。

```text
<!-- XJ_DEV_ENTRY {"schema":1,"entry":"DOTS","execution_path":"DOTS_NATIVE","task_id":"XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1","spec_sha256":"<64位真实摘要>","checkpoint_sha256":"<64位真实摘要>","target_repository":"<任务指定owner/repo>","target_base_sha":"<40位真实base>","code_commit":"<40位真实提交>","event":"CODE_READY"} -->
```

仅接受仓库Owner账户向PR17发布的created事件。未知发送人、其它PR、重复JSON字段、错误摘要格式或隐含Codex路径拒绝。服务端回执为XJ_DEV_ENTRY_RECEIPT；不得将其当作代码执行或停止确认。
重复投递不修改canonical任务，可能有重复机械回执；不宣称本接口已实现账本级去重或自动执行。

## P2人工一次部署交付要求
开发者完成并冻结同一安装包，提供SHA256、依赖检查、verify-only、一个安装命令、一个回滚命令及预期终态。Owner在英国服务器一次执行已审查安装命令；缺依赖时停止并返回准确缺口，不留半安装状态或让Owner猜路径。
人工部署不豁免实现完整性、独立QA／Security／Release、同制品审核、旧新writer互斥、OAuth/TLS真实绑定或回滚实测。自动root执行入口不再是安装包交付前置条件；当前包尚未完成，禁止提供猜测性root切换命令。
