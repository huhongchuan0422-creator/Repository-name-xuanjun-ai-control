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
