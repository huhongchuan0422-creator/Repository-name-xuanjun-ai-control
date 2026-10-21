# 社区预览正式后端接线与现场依赖

本文件是原Issue76的源码接线与待确认候选，不证明现场已安装。现有`deploy/community-preview/server.py`使用fixture、Mock兑换和临时数据，不能作为真实客户后端发布。

## 已有正式入口与配置

`MiniApplication.from_existing_runtime(center, runtime, principals, config, app_secret)`复用宿主已打开的Center与原StageRuntime，不创建Center、数据库、账户、密钥、权限或listener；关闭应用不关闭宿主数据库。凭据由既有宿主受保护入口传入，配置schema不接受Secret字段。实际微信兑换仍使用原WechatCodeClient；不能注入fixture作为真实验收。

`config`必须恰好包含以下字段；真实现场值均待管理方提供原始回执，不能用新建空库补缺。

| 字段 | 合同 |
|---|---|
| version | 整数1 |
| appid | 原小程序AppID；现有源码为wx1d5f8873eaea5392，需核现有账号绑定 |
| https_origin | 受保护HTTPS origin；本任务候选为https://community-preview.wenwenwenyiyiyi.work |
| scenes | 非空scene→{project, principal}；principal是宿主既有对象名，不是客户端自报角色 |
| stores | center/orders/merchants/ads/refunds/quotes/saas_orders/modules的实际绝对文件路径；与已打开连接的main路径一致，文件和直接父目录属当前服务用户且无其他用户权限，不允许内存库或符号链接 |

scene必须指向现有CUSTOMER Principal及当前有效、同租户原项目。原Center负责微信身份绑定和会话，原运行时负责订单与数据。新入口不导入CRM、不自动授予任何账户访问权。

宿主调用顺序：取得原持久对象与受保护配置→from_existing_runtime→原configure_onboarding/configure_operations/configure_commerce→原configure_wechat_applyment→仅对已获JSAPI准入的门店调用configure_payments_from_applyments→按已核Nginx身份与受保护origin调用listen_proxy。存在其他已启用模块时继续调用其原configure方法，不复制系统；缺原对象或现场配置即停止，不能用fixture补齐。当前仅为可调用组合API，不是已部署的现场服务启动器。

支付admissions是已知scene的非空子集，未选门店没有支付配置；同店多scene继续幂等。可信FINISHED查询须经过原RSA验签与原持久记录，再投影sub_mchid；受保护JSAPI/分账产品资格独立校验。状态查询当前是审核员主动wechat_query，自动轮询尚未实现。

## 一次性现场依赖与确认范围

以下动作均未执行。Owner确认后，由原国内现场管理方/唯一发布Writer执行；源码窗口只准备候选与检查，不自行操作服务器、DNS、凭据或Actions服务器命令。

| 目标与待核证据 | 最小动作候选 | 影响 | 回滚/停止点 | 责任方 |
|---|---|---|---|---|
| community-preview.wenwenwenyiyiyi.work；公开路径已有502/503观察，但根因未知 | 只读核DNS目标、TLS证书、Host到独立Nginx路由、/community/health；不改主域 | 只读网络请求 | 保存原响应与时间，不因失败重启任何服务 | 国内域名/运维管理方 |
| 国内候选iZvt5t8tlrm8oiZ；xuanjun-community-preview.service、/etc/nginx/conf.d/xuanjun-community-preview.conf、/run/xuanjun-community-preview/preview.sock | 只读核单元/路由/socket存在与当前状态、有限脱敏错误日志，定位拒绝连接层 | 不启动/停止或重载；不读取环境变量/密钥原文 | 留原版本/状态/文件摘要；身份或路径不符停止 | 原国内现场管理方 |
| 原Center与8个store路径、schema/版本、非空历史、备份、当前占用者 | 管理方提供准确对象创建入口、路径、服务UID/GID、锁/单Writer与备份回执，再离线核config | 不迁库、不初始化、不修改原数据 | 未找到历史或所有权不明即停止；保留原数据库 | 原客户中心/数据管理方 |
| 原AppID、AppSecret引用、真实code2session出口与原账号openid绑定 | 只核既有secretRef与受保护读取入口可用，不展示/复制密钥；用原绑定流程验收真实身份 | 登录验收需单独确认测试账号及审计 | 失败保留未绑定/未登录；不自动绑定或放宽权限 | 小程序账号/身份管理方 |
| 真实正式组合服务候选 | 在上述证据齐全后，准备固定SHA版本、隔离路径、原配置引用、唯一Writer与备份，再交Owner确认最小发布变更 | 仅独立预览服务；不得发布现有fixture server冒充真实后端 | 切回原已备份版本/单元/路由/状态；未知副作用先核对，不盲目重试 | 唯一发布Writer；Owner批准 |
| request合法域名、预览访问身份、同版本真机页面与登录业务 | 管理方核现有合法域名；真机验证本人资料/门店/订单，留同版本证据 | 如需修改账号安全设置，另列精确字段交Owner确认 | 配置变更前保存原值；失败不发布客户验收码 | 小程序管理员与Owner验收方 |
| 真实商户FINISHED/JSAPI/可选分账、资金与Finance | 单独提供渠道资格与资金验收方案；本轮不触发 | 不影响本轮源码完成 | 资格缺失保持payments=false；Finance UNCONFIRMED | 商户/财务/Owner |

先完成只读定位，再按真实根因提交最小变更，不把整张表当作已经授权的现场操作。HTTPS健康READY只证明进程和数据库连通；真实微信身份、持久数据及同版本业务旅程未核验时，客户验收仍未通过。保留BACKEND_NOT_READY硬门禁，不生成不可用新码。
