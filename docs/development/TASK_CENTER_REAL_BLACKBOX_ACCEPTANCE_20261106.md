# Task Center 真实联调与黑盒验收合同（源码增量）

状态：**SOURCE_IMPLEMENTED / NOT_DEPLOYED / NOT_ACCEPTED**。本增量只记录合同、
证据引用和发布门禁，不发起真实验收、部署、证件处理、支付或外发。

## 顺序和同版绑定

后续项目必须按以下顺序推进：

1. `FRONTEND_BACKEND_INTEGRATION`：绑定同一前端 commit/build/app version，
   后端 commit/image/API schema、环境和真实入口；记录独立联调负责人、时间、
   证据与阻塞。
2. `PRODUCT_ACCEPTANCE_AI`：只有联调最新记录为 `PASS` 后才能登记；再对同一
   版本组合、环境、入口、制品和隔离 SecretRef 元数据做真实黑盒验收。
3. Release Gate：两道门最新记录均为 `PASS` 才返回 `PASS`。任一
   `FAIL/BLOCKED/NOT_TESTED`、异版、异环境、入口不可用、缺隔离证明、缺证据或
   未清阻塞均 fail-closed。

状态集合固定为 `PASS / FAIL / BLOCKED / NOT_TESTED`。修复后的 PASS 必须引用
上一条非 PASS 记录，并使用计划冻结的同一版本组合复测相关和受影响流程。运行记录
只追加；相同 `run_id` 的不同内容被拒绝，历史不覆盖。

## 联调清单

完整覆盖：真实请求合同、认证/session、权限、字段/编码、上传大小与超时、幂等与
重复提交、错误码与用户反馈、持久化、异步任务/回调/轮询、退出重进与跨端一致性、
弱慢网、失败恢复。前端单测、后端单测、各自 CI、API mock 均不能替代。

## 黑盒清单与角色

计划冻结前端负责人、后端负责人、联调负责人、验收负责人和 Release 负责人；至少
四个不同主体。黑盒清单覆盖真实入口、角色矩阵、SecretRef 隔离、环境和制品绑定、
主流程、失败流程、证据完整及阻塞清零。CI、单测、mock、二维码和纯截图证据均被
拒绝。只保存 SecretRef、用途、环境、隔离范围和隔离证明引用，不保存真实秘密。

## 历史项目与首个模板

不追溯改写旧记录。没有新计划的旧任务保持
`LEGACY_RECORD_NO_REAL_ACCEPTANCE_PLAN`，不会自动升级为真实 PASS。本次社区项目
首个模板为 `COMMUNITY_REVENUE_SHARE_ADMIN`（社区分账管理后台），可明确登记
`LEGACY_NOT_RETROFITTED`，其 `pass=false`，不得冒充联调 PASS。小程序仅显示
“小新负责 / REFERENCE_ONLY”，不会创建小程序任务。

禁止在计划、证据或 UI 中录入真实证件、支付数据、原始 Secret 或执行外发。

## 安装与回退

安装候选时由既有 Task Center 启动流程执行 SQLite `CREATE TABLE IF NOT EXISTS`，
新增 `real_acceptance_enforcement`、`real_acceptance_plans` 与
`real_acceptance_runs`，不修改旧表。新建任务会写入 enforcement，缺计划时验收
fail-closed；历史任务没有该标记，保持兼容但不升级为真实 PASS。上线前应备份同一
SQLite 文件，并在预发布环境验证旧任务投影和新门禁。

回退应用代码时保留两张新增表，旧版本不会读取它们；这样可保留 append-only 证据。
不得为回退而删除或改写运行历史。若需重新启用新版本，使用原数据库即可恢复投影。
