# 原Owner站点服务端候选（未发布）

接续原Work17／PR72，重点补第15项中文Owner摘要的真实服务端代码缺口；不增加任务。
原项目、单Owner访问策略、自有域名和原107个资料资源保留。

`worker.mjs`实现Sites Worker fetch入口，而非独立HTTP listener：
`POST /api/work17/read`只接受一个literal task_id；使用Sites Dispatch注入的站点用户ID
与服务端配置的精确Owner ID比较，拒绝缺身份（包括service bypass）、不同Origin和参数注入。
仅服务端持有英国Bearer，固定HTTPS地址、禁止重定向、5秒超时和输入/响应字节限额。
失败统一503/HOLD，不将旧缓存作为成功。响应仅投影七视图状态、任务数和扫描完整性，
不输出原始回执、内部路径、凭据或执行权限。没有修改告警sender、账本或执行权。

## 英国接线合同（现有端尚不具备）

地址：`https://uk.wenwenwenyiyiyi.work/api/work17/read`。
英国现有可信controller必须认证服务凭据并实施固定Owner与每task权限，
调用已审OwnerFoundationController和原受保护connection supplier。
成功响应必须为`{schema: "WORK17_OWNER_HTTP_V1", task_id, snapshot}`；
snapshot是原read_owner_foundations结果。task_id由服务端从该次已验证请求绑定，
不能采用任意客户端自报身份。原GET /api/state不符合此合同，候选会拒绝其响应。
snapshot绑定、真实descriptor/producer以及读取前后授权仍由英国原控制器验证，
前端的status/digest校验不能替代此事实。本候选不是已部署的英国endpoint。

## 配置与迁移

部署后由Sites Dispatch可信边界提供身份头；裸Worker／直连可伪造身份头，禁止当作独立认证服务。
不得从平台account ID或邮箱猜测`WORK17_OWNER_SITE_USER_ID`，须取真实受保护会话的站点范围ID。
`WORK17_UK_READ_BEARER`只能通过原服务端secret配置，禁止出现在Git／HTML／URL／浏览器。
这两个配置当前不存在，不能宣布登录或真实通道通过，也不创建新凭据。

build.mjs从原站点精确HEAD16b6113d6d8c98eda8f646437d5ef1f54a9345ba读取107个tracked dist资源，
逐字节嵌入单个Worker，输出逐资源SHA256映射。使用原Git对象字节，不读取运行时或凭据。
迁移时在原Sites source repository保留资料与身份，按Sites支持流程移除static声明并输出
dist/server/index.js；本PR不修改原Site hosting.json，不上传或发布，不在公开控制仓库复制私有资料内容。
生成文件仅用于本地候选验收，不提交原站点内容。

```sh
node build.mjs /absolute/pinned/site/checkout /absolute/candidate/generated
WORK17_GENERATED_SITE=/absolute/candidate/generated node --test test-worker.mjs
node --test test-worker.mjs
```

本地真实原资料构建107/107字节校验及10项检查通过。
Hosted只使用1个显式fixture资料资源并测试请求／响应拒绝，不冒充真实站点发布或107资料Hosted验收。
原Python84项不因本候选在本地重跑；精确新commit的Hosted结果须另取。

## 集中独立审查范围及剩余门禁

请独立审核Worker代码、builder原资料保留及secret/身份/原controller信任边界，
重点检查跨Owner、跨任务、异常、响应限界和旧快照不冒充实时。作者不自批。
P2实际完成和独立验收、英国原handler现场接线、真实Owner ID／task ACL、secret通道、
真实producer/通知ACK/Canary、Sites正式构建／浏览器／UK链路均PENDING。
第2—5项看板UI正式接入仍等P2完成；当前只准备服务端候选。
生产部署授权未取得，PRODUCTION_RELEASE=NOT_GRANTED。
