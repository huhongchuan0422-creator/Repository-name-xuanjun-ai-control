# 玄钧网站销售与共建入口：隔离静态候选

本目录为CHATGPT_NATIVE新增、完全隔离的静态页面候选，不覆盖国内现有官网或Work网站源码。所有页面包含noindex以及非生产提示。不得将文件直接拷入生产根目录。

目标URL: /marketplace/（产品销售）、/visual/（可视化）、/visual/community-payment/（已有演示路由）、/ecosystem/（共建共享）、/customer/projects/（受控客户项目）。首页index.html只用于导航方案和预览，不允许替换已有官网首页。正式首页导航由原网站Owner在准确1187文件基线中最小接线并通过多语言/旧深层URL测试。

当前社区角色源码：demos/community-local-e2e/**。联合制品需将其统一发布为/visual/community-local-e2e/**，并核对其中的相对脚本引用，否则演示入口可能404。该工作需要原站发布通道和独立审核。

生态规则依据docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md §7.7(V2.3)：2000万ECV、交易900万+活动1100万、创始600万+共建1400万是不同维度不得相加；普通来源ECV每份一次性500元专项抵扣额，购包赠送ECV无额外500元；自营合格服务费最高90%抵扣；活动、Web3、治理、未来价值共享均未上线。不得按旧“每份100元”规则公开营销。

本候选不收集个人信息、不发起订单/支付/领取/资金变更；具体产品销售、真实客户项目及反馈以认证、Finance及发布验收为准。

验收清单：所有链接及资源无404；真实多语言官网最小导航接线；旧深链不变；移动端；所有页面真实HTTPS；未登录ChatGPT浏览器；演示身份隔离；销售价格从批准Price Book读取而不是静态造价；公开合规和独立审查；可回滚。状态OFFLINE_CANDIDATE/NO_PRODUCTION_DEPLOYMENT。
