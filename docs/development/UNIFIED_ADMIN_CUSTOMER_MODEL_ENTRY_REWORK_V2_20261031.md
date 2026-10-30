# 统一后台 · 模型服务边界纠正 V3

状态：`UI_CANDIDATE / OWNER_CONFIRMATION_REQUIRED / NOT_DEPLOYED`

本增量只返修 Owner 否决的模型服务入口，不改变已确认的统一后台外壳、十一项
一级导航、七个固定管理模块、项目/审核页面、Identity/CRM 边界或数字孪生引用。

## 返修结果

- 管理员 `#config-models`：首屏仅呈现模型服务状态、风险和证据；
  Provider、OpenAI 执行通道、用量估算全部默认折叠，避免长技术表单。
- 撤销 6cd0a569 误加的 `#customer-model-service` 路由、页面、交互状态与后台跳转；
  两种服务方式属于官方网站的客户购买与配置流程。
- 两种服务方式不创建第二套后台，不改变 `API_FIRST` /
  `SUBSCRIPTION_OAUTH_FIRST` 的既有执行通道语义，也不新增写 capability。
- 所有真实平台、OAuth/API、安全录入、订单、权益、用量、账本和模型调用仍为
  `NOT_IMPLEMENTED / NOT_CONNECTED`；本候选没有部署或安装。

## 需要 Owner 确认的受影响页面

1. `#config-models`：管理员摘要的三项指标、默认折叠层级和官网边界文案。
2. 独立证据原型：官方网站模块选择、购买与配置流程；不属于后台路由，未修改
   官方网站源码，未部署、未验收。

其余已确认页面未改版，不重复索批。
