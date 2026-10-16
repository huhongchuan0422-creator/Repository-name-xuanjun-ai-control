# 玄钧云汇多定制项目独立动态展示与交付后模块上架 V1

Owner确认：未来可以同时开发多个定制项目；每个项目单独展示。沿用原PR122、现有动态展示/受控发布机制、Project State、Module Registry、Product/Offer Catalog、Finance、Price Book、审核及版本证据；不建立第二套展示引擎、商品库、客户身份库。官网一级导航归Work；ChatGPT负责各项目二、三级页面和功能展示。

## 多项目同时开发
每个项目使用稳定project_id和独立详情/预览入口。项目A/B/C并行开发互不覆盖进度、权限、客户资料或演示版本。一个项目内每项最小功能具有feature_id、source_commit、CI、independent_review、preview_artifact_sha256和approved_preview_version；只有通过测试、独立审查、客户公开授权与隐私检查的功能，才由既有发现/发布器自动更新该项目的可视化页面。失败、UNKNOWN或未授权的功能保持内部HOLD；已有已审核预览版本继续正常服务。用户能看到真实的已完成功能、可体验入口、待办及时间证据，不宣称未经审核功能完成。

功能预览状态：DRAFT→TESTED→INDEPENDENT_APPROVED→PREVIEW_PUBLISHED（失败为PREVIEW_HOLD）；项目状态：REGISTERED→DEVELOPING→CUSTOMER_REVIEW→DELIVERED→MATURE_CASE，状态彼此独立。多个项目独立进度、独立案例与导航；不要求Work每次为新增页面手工更改一级导航。是否自动公开由原受控Release Gate决定，不能因git push直接公网展示。

## 全项目交付后的模块复用
项目达到DELIVERED+客户交付验收后，自动触发通用能力盘点；逐一核查IP归属、客户专属限制、第三方许可、数据脱敏、依赖、独立封装与租户隔离。仅拥有合法复用许可的最小通用模块进入REUSE_CANDIDATE→RIGHTS_VERIFIED→PACKAGED→TECH_AND_SECURITY_APPROVED→COMMERCIAL_READY→RELEASE_APPROVED→MARKET_PUBLISHED；任何一项不合格为SHOWCASE_ONLY/NOT_FOR_SALE。基础账号、登录、个人资料编辑等既有玄钧自研模块不因被某项目引用转为该项目共创资产。

各模块使用唯一module_id，能被不同项目引用但不能复制产品台账。Manifest绑定原项目/版本、IP授权、依赖、兼容性、哈希、真实CI、独立审核、业务权限、双币价格、成本、合同、发布批准及演示链接。自动上架指门禁通过后由原发布器执行，无需人工改导航；不是项目交付当天不经审批就销售。支持既有月付、买断、0元、按量和多币定价/独立服务费；缺成本或有效价格不收费。已有已售客户权益和历史定价不得被新版本覆盖。

## 验收
同时登记项目A/B，A新增审查通过的功能只更新A页面，B不变；功能未审或客户拒绝公开则不出现在公网；版本回滚保持上一个已批预览；整个A项目交付后具备合法许可的模块自动进入封装门禁并在商务批准后上架，B未交付不误上架；同一模块多项目引用只保留一个canonical记录。真实CI、网页浏览器、独立审核、发布与回滚回执分别取证。当前仅规则登记，未证明生产自动发布或市场上架已经接线；原PR122生产门禁HOLD，P2/PR17不变。
