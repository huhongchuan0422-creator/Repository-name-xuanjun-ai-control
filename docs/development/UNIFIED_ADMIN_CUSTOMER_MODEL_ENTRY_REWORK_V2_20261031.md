# 统一后台 · 客户模型服务入口返修 V2

状态：`UI_CANDIDATE / OWNER_CONFIRMATION_REQUIRED / NOT_DEPLOYED`

本增量只返修 Owner 否决的模型服务入口，不改变已确认的统一后台外壳、十一项
一级导航、七个固定管理模块、项目/审核页面、Identity/CRM 边界或数字孪生引用。

## 返修结果

- 管理员 `#config-models`：首屏仅呈现模型服务状态、风险、证据和客户侧入口；
  Provider、OpenAI 执行通道、用量估算全部默认折叠，避免长技术表单。
- 客户侧 `#customer-model-service`：在同一后台外壳中用两张选择卡表达“自带
  上游账号”和“购买玄钧AI新 API 服务”。付款、凭据、权益、计量和账单边界
  仅在“查看费用、凭据与权益边界”中展开。
- 两种服务方式不创建两套后台，不改变 `API_FIRST` /
  `SUBSCRIPTION_OAUTH_FIRST` 的既有执行通道语义，也不新增写 capability。
- 所有真实平台、OAuth/API、安全录入、订单、权益、用量、账本和模型调用仍为
  `NOT_IMPLEMENTED / NOT_CONNECTED`；本候选没有部署或安装。

## 需要 Owner 确认的受影响页面

1. `#config-models`：管理员摘要的三项指标、默认折叠层级和客户侧跳转。
2. `#customer-model-service`：两张选择卡、首屏文案、选择态和边界详情。

其余已确认页面未改版，不重复索批。
