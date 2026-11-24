# 蜜柚推荐/详情增量（2026-11-24）

实际模型 openai/gpt-6.1-sol，未回退。已读 xuanjun-development、两篇防回归和开发9.3。main已提供旧 f0e/run9970 因429终止、末动作只读、无同域writer核证，本轮唯一源码writer。

## 来源与纠正
之前 SOL-0906-SOURCE-BLOCKER 将 dc15cc00 误当工作树必须HEAD，现撤销该判断，不以之阻断开发。
原 origin 为 huhongchuan0422-creator/Repository-name-xuanjun-ai-control。
原 dirty 工作树仍在 workspace/.runtime/sp-offline-repair-20261111/repo，HEAD 71a7dace、repair/current-rebind-v10-20261111，未切换、覆盖或提交其dirty。
dc15cc00a14bbd0e8ee090bb404d1d6f0e74b317 是远端原 feature/chatgpt-community-wechat-sp-offline-20261017 ref；它与71a7的共同祖先为d80f7374。
最新原上传工作流成功Run 44412692244，control c61e34235d798c46fd82e8310207675095202c54，官方回执 DEVELOPMENT_VERSION_UPLOADED，开发版 hz-c87e93741357。实际产品是51文件Hangzhou快照，不是任意工作树mini目录；原manifest c87e9374135797329d35303dfa8a527e3b4fc680f49db126e4f667fecbff613f，archive 4f88d86abfb28e95481039e227ee09023309b040d185fd186a78ab12abf07b74。
该快照存在于dc15 git tree内 deploy/community-preview/hangzhou-snapshot/，原checkout JS/WXML与dc15 canonical源码逐字节一致。故在dc15独立稀疏worktree延伸，不用c4b候选作权威。

## 最小实现
复用真实 customer.directory → customer.store 链路和 platform_showcase/showcase_item 合同，不新增API、账号、权限、门禁或交易路径。
推荐标识“仅展示·无交易”；点击详情展示真实商品名称、说明、元/份、库存、四图及作者/来源/许可/非本批实拍。四图存在时不重复渲染主图；没有gallery的旧记录保留单主图。
仅展示分支无下单、付款或跳转门店交易事件，沿原read token/generation失效保护。原普通门店/平台自营/原商品目录路径保留。
更新原上传快照恰好三个checkout文件、对应manifest/zip和原builder pins；48个其余快照文件不变。旧独审引用只覆盖旧快照/后端，pair元数据明确本增量仅作者自测，未冒称独审。

原已审后端展示候选漏投影quantity；随附 pomelo-showcase-quantity.patch，仅把已存quantity加入public detail，不改写商品。补丁针对原handoff backend/community_platform_showcase.py（尚未安装）而非旧repo同名猜测。未覆盖旧包、未写运行树，交原安装者并入原候选四文件。未并入时客户端库存显示“待同步”，不捏造100。

## 直接回归证据（离线，不是真机）
- 原推荐、原storefront、原商品目录及新showcase测试：61/61通过。
- 实际最终51文件快照载入新详情测试：6/6通过；包括原四图草稿经原showcase公共投影+quantity单字段补丁→详情，真实素材哈希/署名、10元/份、100份；使用合成身份，未写业务数据。
- 原snapshot prepare/build实际入口及51文件hash核对：通过；两个identity regression通过。快照三个checkout与canonical字节一致，其余48文件原上传身份未变。
- git diff --check通过；没有重跑不相关长套、安装依赖或克隆整仓。
- 新manifest 1877e83c8e78fe7cc15fe25ac8d9be8193fc3ff41c9d3e85bb6c586b4af93f92；新archive 69b8c4c9647a51912be10ff3e68eb32aae78fc89dcee49c21746f32222f85b33。

## 未完成/恢复边界
本轮未开发版上传、未后端安装/商品发布、未真机验收；未提审、未正式发布、未绑店/支付、未改收款码文件、不查英国归属。
沿原安装者路径接 quantity 单字段差异及原展示候选，版本查重后发布原商品；原合法开发版通道可消费本快照，随后真实微信推荐→详情验四图、10元/两只/份、100份、无交易。既有后端/商品安装状态不因本离线通过改变。
代码恢复可反向应用本增量；不涉及配置/数据写入，不能把代码恢复称数据回滚。
隔离source工作树约13.5MiB；磁盘87%，检查前后全局used下降约95MiB（有其他并发系统活动，非本任务净delta）；未装生产。
外部证据在 workspace-developer/deliveries/community-pomelo-20261124/{upload-44412692244/,direct-regression.log,snapshot-regression.log,snapshot-identity-regression.log}。
