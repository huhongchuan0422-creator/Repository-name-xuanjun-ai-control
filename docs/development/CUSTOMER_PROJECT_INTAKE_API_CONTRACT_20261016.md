# 玄钧云汇客户项目资料中心：前后端交付契约

Owner：ChatGPT负责二三级页面、资料条目与流程；Work负责正式登录、项目授权、加密材料存储、SecretRef和网站发布。本文件不授权新增账号数据库或生产写入。状态：SOURCE_CANDIDATE / NO_AUTH / NO_UPLOAD / NO_DEPLOYMENT。

## 项目数据只读响应
`GET /api/customer/projects`：必须使用服务器认证会话中的subject获取有权访问的项目，客户端不能传customer_id代查。
`GET /api/customer/projects/{project_id}/requirements`：每个条目提供requirement_id、title、purpose、required、instructions、official_url、sensitivity、submission_method、state、revision、reviewer_decision、updated_at。仅返回对应Project+Tenant授权的资料，拒绝非项目成员。
`GET /api/customer/projects/{project_id}/requirements/{requirement_id}/history`：按权限返回已保存的提交及审核事件；普通客户不可见其他客户或内部隐私审查。

## 正式写入接口（Work建设前全部禁用）
`POST /api/customer/projects/{project_id}/requirements/{requirement_id}/drafts`：原合同客户或经其授权的project_editor；CSRF、会话、租户、项目ACL、审计及修订版本ETag/If-Match；幂等键必须绑定actor/project/requirement/revision。
`POST .../submit`：仅该项目的有效草稿可提交，服务端扫描非敏感附件并生成不可变提交回执；缺材料保持PARTIAL。
`POST .../review`：仅独立授权reviewer操作，拒绝客户自审；允许ACCEPTED和NEEDS_CORRECTION，强制原因/版本绑定。
`POST .../revoke`：Owner/权限管理员撤销项目成员访问；撤销后所有历史下载URL和未完成上传token均失效。
所有跨租户/跨项目/伪造请求身份、仅凭合同编号或邀请链接、旧rev重放、重复审核均拒绝。UNKNOWN副作用必须对账，不能盲重放。

## 材料存储与敏感项
普通资料：经授权的私有上传会话，文件格式/体积限制、恶意代码扫描、对象加密、访问审计、到期处理与短时下载链接；客户仅访问其项目。真实文件、银行账号/证件不得进入GitHub、ChatGPT文件库或未经审核的静态演示。
API Key/私钥/AppSecret/Token：普通上传路径强制拒绝，只能可信OAuth或Secret Portal→SecretRef；前端仅展示已验证/到期/需更新的状态，不回显密钥。

## 业务状态
NOT_STARTED→PARTIAL→SUBMITTED→UNDER_REVIEW→ACCEPTED；SUBMITTED/UNDER_REVIEW→NEEDS_CORRECTION→PARTIAL；每个状态事件记录actor、时间、revision、来源和审批意见。只有授权审核员可置ACCEPTED。逐项可分批；单项目总状态由权威条目聚合计算，不信任客户端直接提交百分比。

## 实际部署验收
真实未登录浏览器不得访问私有详情；原合同用户可见，未授权账号、跨项目成员、已撤权成员都拒绝。浏览器刷新、断网和重启后草稿可恢复；恶意文件、过期签名、重复提交、审查并发、变更代表、材料到期及删除导出请求均须有负面测试。Telegram/飞书/网页AI首次通过站内短时挑战绑定，未连接时显示PENDING。

## 权威状态与权限矩阵（R1/R2）
NOT_STARTED --save_draft(customer)--> PARTIAL; PARTIAL --save_draft(customer)--> PARTIAL; PARTIAL --submit(customer)--> SUBMITTED; SUBMITTED --start_review(independent_reviewer)--> UNDER_REVIEW; UNDER_REVIEW --approve(independent_reviewer)--> ACCEPTED; UNDER_REVIEW --request_changes(independent_reviewer)--> NEEDS_CORRECTION; NEEDS_CORRECTION --save_draft(customer)--> PARTIAL。其他边全部拒绝；审核员与当前submitter不得相同。提交者无审核权限，审核员不得使用客户动作。页面仅提供客户侧模拟，不能模拟审批。客户按钮在状态不允许时禁用，动作函数仍独立拒绝越界调用。

## 并发、幂等及UNKNOWN确定性对接契约（R4）
- 每个动作必须携带operation_id（租户/项目唯一）、Idempotency-Key、If-Match revision、规范化payload_digest及可信actor。服务端不得使用请求提交的actor/tenant字段作为身份。重放同键同摘要返回首次持久提交的相同结果及版本；同键不同摘要报409 IDEMPOTENCY_CONFLICT；另一操作使用旧revision报409 VERSION_CONFLICT且不产生业务状态变更。
- 单个数据库事务内重新检查当前actor有效会话、项目成员及撤权纪元、原合同客户绑定、审核员独立性、最新revision、合法转换；先写状态事件、不可变提交版本、审计和幂等结果，再commit。事务外预检不能代替事务内授权。两个客户端同revision并发只有一个操作可提交，另一个409；相同幂等键只记录一次。撤权与提交竞争按事务序列化先后确定：撤权先提交则旧权限提交拒绝；提交先成功则保留历史记录但后续访问立即失效。
- POST响应丢失或超时返回UNKNOWN，不可盲重试。提供经同一项目授权的GET /operations/{operation_id}，返回COMMITTED(原回执、revision、payload_digest)、NOT_APPLIED（经权威账本及无未决事务证明）、UNKNOWN（尚不能确认）三种；同键同摘要可只读重取原回执，不追加副作用；UNKNOWN保持阻塞，待恢复对账。
- 文件先上传到与tenant/project/actor/revision绑定的隔离临时区（最大大小、允许类型、扫描、有效期、加密）。上传完成不表示材料已提交。扫描未过拒绝并安全清理；对象已成功但业务事务失败/UNKNOWN时保留隔离对象与操作账本，禁止直接发布下载地址，由有界清理任务在核实没有有效引用后删除；失败清理记为待人工处理。对象记录和业务提交回执有可核对的存储键/hash/操作ID；生产集成须测试崩溃、重启、回执丢失、扫描失败、部分成功。
