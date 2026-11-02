# 安全输入页原任务源码交接给 OpenClaw

Owner 于 2026-11-02 明确要求通过原 GitHub 交接当前成果，由原 OpenClaw 接下来做。本目录仅保存已存在候选与证据，不是生产发布批准，不新增执行通道或凭据库。

## 接续与唯一责任
本端源码 Writer 和现场执行者均已冻结安全页新增写入，无本端运行中任务。原仓库其他未提交或后台状态 UNKNOWN，不覆盖。原 OpenClaw 接收后请在 Issue 19 回复准确 commit/tree、取件校验、原任务/session/run 与接任 ACK；已有同任务先核在途，不重复派。此处发布不等于已接收。

## 已有实现及证据
固定原 OpenClaw 2026.9.9 基础：手机三字段遮罩输入、600 秒、原授权后的请求桥、原 Store 批量写入、同一状态数据库中的无秘密持久请求回执、UUID revision（不改 actor 审计）、私有浏览器消费候选。10 个原框架文件的修改在 native-framework.patch；新增小模块在本目录。不要用上游 dist 整包覆盖现网 B7/403 修复。

CURRENT_NATIVE_CANDIDATE_MANIFEST.json 是冻结的完整本地候选清单，包含未重复上传的 patched-source 文件。发布字节以 PUBLIC_SOURCE_MANIFEST.json 为准。原修改文件可从固定上游加 patch 还原；本地构建器/部分测试包含参考路径，接手方须映射固定原源码后执行，不能当现场安装器直接运行。

已有隔离测试：Python 41；Store adapter 12；原 Store kernel + 真实 SQLite 11；持久 receipt + 真实 SQLite 31；browser policy 12；gateway bridge 18；native patch 13；native UI 18；Store revision 19；private consumer 24。独审已关闭错请求 ID、取消生命周期、COMMITTED 误取消、PENDING 误投影、重复建表、UNKNOWN 重复提交、同毫秒版本碰撞等问题。manager/auth/浏览器/隔离边界仍含测试替身，故障注入不等于 OS 强杀；这些不是 Hosted CI、Gateway、手机或生产验收。

## 未完成，不能省略
1. 现有 HTTPS 下手机可用的认证入口/配对桥未证明。PUBLIC_HOST_OBSERVATION.json 是脱敏屏幕观察，不是原服务器 JSON。现有 Owner API 为 Bearer，不等于已有手机 cookie；不要放永久 token/setup code 到 URL，不关闭 token/device/auth 门禁，不暴露整个 Gateway。
2. 原框架接线、同库 metadata schema 的原迁移登记、现网版本兼容、备份/diff/语法检查/受控加载及回滚未执行。
3. 原生浏览器仍为 BROWSER_SECRET_INJECTION_UNSUPPORTED。私有 consumer 不是已实现的可信原 context 输出/网络隔离适配器；原 console、trace、DOM、截图、网络、下载、screencast、CDP 等泄漏面必须实际处理，不能仅凭 quarantine 登录称页面 QA 完成。
4. 先非敏感 canary 验完整闭环：手机可打开、三框可填、10 分钟过期、一次提交、防重放、重启后 Ref 仍在、更新/删除、所有日志/工具/模型/截图无明文，以及原验收浏览器安全登录和后台页面核对。未通前不得收正式凭据。

原 Store 已有静态明文 SQLite 与软删保留语义，接手时须如实评估和披露，不称已加密或即时物理删除。初始 allowedHosts=[]，核准实际社区 HTTPS hostname 和必要当次权限后才最小设置。

正式凭据名称仅 COMMUNITY_ADMIN_ACCEPTANCE_URL、COMMUNITY_ADMIN_ACCEPTANCE_USERNAME、COMMUNITY_ADMIN_ACCEPTANCE_PASSWORD。只供社区后台验收，不增加支付、退款、分账执行、云资源或系统配置权限。不得读取/复制韩国币安真实秘密或混用金融凭据库。

## 当前完成口径
尚未创建可用公网输入链接，未部署，未收取真实凭据，未做完整浏览器注入验收。不要让 Owner 下载源码包或自行安装；按原任务继续到实际可用验收，真实安全权限/部署门按原要求处理，不伪造批准或复活旧 permit。
