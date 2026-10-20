# PR122 飞书客户对话对接候选

## 1 设计与任务归属

Owner 于 2026-10-20 授权认领飞书客服对接；认领记录：
https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/122#issuecomment-6284557881

依据 customer-intake 分支提交 db10932b265d8986025cd94c54576b483208e853 的
`UNIFIED_CRM_CHANNEL_REFERRAL_REUSE_20261016.md` 和
`PUBLIC_BRAIN_CONTEXT_KNOWLEDGE_ISOLATION_V1_20261016.md`：Telegram、飞书和网页 AI
复用统一客户身份与项目上下文。此候选以 PR122 site-hub 提交
9488439a38a611a792b7fc31d38f4e95816c5658 为基础，不另建 CRM。

只实现专用客服自建应用的签名 HTTP 回调适配；不冒充商店多租户应用或 WebSocket 实现。
韩国 OpenClaw 的 Owner 机器人、开发机器人和认证通知机器人属于保留身份，不复用其 app/token。
服务端 scope 显式提供 app_id、tenant_key、允许发送方租户和三种保留应用 ID；未知映射拒绝准入。
初次 scope 只允许绑定没有飞书历史的原数据库；已有历史需独立核实迁移，不静默认领。

复用原 Providers 的签名、时效、AES、token 校验和发送器，补充租户、用户、消息类型和严格 JSON 校验。
依照飞书官方消息事件说明，按 app+tenant+message_id 去重，避免同一消息不同 event_id 重复回复：
https://open.feishu.cn/document/server-docs/im-v1/message/events/receive

绑定沿原 provider challenge + 登录网页确认；项目必须明确指定，禁止仅凭 open_id 自动合并客户。

## 2 开发接线与运行边界

新增 `scripts/pr122_feishu_customer.py`：

- `CustomerFeishuProviders(config, scope)`：专用客服身份和消息验证。
- `admit_scope(center, providers, deployment_profile=FULL)`：受审准备调用，写原 settings/audit；无公网准入接口。
- `make_app(factory, providers, origin, assets, deployment_profile=FULL, ...)`：包装原 HTTP App，沿原 `/customer/center/webhooks/feishu`，不新增监听器。
- `prepare_next_reply(center, providers, deployment_profile=FULL)`：一次有界 worker 步骤，原 ai_jobs 持久写 UNKNOWN 后调用原 local_ai；成功写原 WEB_AI 来源证据和 FEISHU PENDING 出站记录。
- 再由原 `providers.drain_message(center)` 发送；API ACCEPTED 仅代表渠道受理，不代表客户已收到。

回调只归档，不同步调用模型。模型上下文携带 user/project/tenant/customer，完成后重新验证成员权限及绑定。
超时、进程中断或结果不确定保持 UNKNOWN，不自动重试模型或出站发送。原证据链关联入站、AI 输出与出站。

此提交不改原共享 Provider/Core/HTTP/ops、发布器或现有服务。新增 workflow 使用 GitHub Hosted runner 和合成数据。
LOGIN_ONLY 继续禁止客服消息与 AI；此适配明确拒绝在 LOGIN_ONLY 挂载。
原运维 factory/worker 尚未接入此候选；不能直接运行现有 install 命令冒充完成接线。

## 3 验收与真实联调条件

本地/CI 覆盖签名、租户身份、重复投递、双重绑定、权限撤销、超时 UNKNOWN、AI 来源证据、原 HTTP 路由及原发送器。
合成 RPC 与模拟飞书返回不等于真实模型/渠道验收。CI 产物绑定提交、tree、测试数量和文件哈希。

真实启用前仍需：

1. 确认专用客服飞书应用与保留应用的准确 ID/租户映射；密钥通过原受保护配置 SecretRef 注入，不贴到评论。
2. 确认原客户中心运行目标及 FULL 上线门禁；沿原集成窗口加入 factory、worker、打包闭包，不能解除 LOGIN_ONLY 来偷跑。
3. 核实本地 AI socket、peer UID 与批准的模型映射；本候选不替换模型，不把 fixture 当 GPT-5.6-sol 证据。
4. 真实测试客户完成网页登录确认、飞书收消息、同项目 AI 回复、去重、撤权、记录同客户归档及回退验收。

状态：CANDIDATE；真实凭据未使用、生产服务未变更、客户飞书未宣称上线。
