# 国内自媒体接续验收记录

2026-11-25，亚洲上海时间。发布全链路仍待验收。

## 源码和运行证据

- PR #122 是开放草稿。候选基线为 `7e2d3d02587feaee28921671c7d8898e84d732de`，原维护分支为 `feature/stage5-next25-integration-20261015`。原 Codex 工作区交出的合成测试已复用。正式环境写入人仍待原通道确认。 [PR #122](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/122)
- 隔离分支 `codex/media-tiktok-refresh-20261125` 的代码提交为 `b2e32219a1b6409067e52aff4317a13af945dd36`。候选包新增 TikTok 续期请求及内部续期入口。按原绑定取得 SQLite 续期执行权，成功时原子替换整对凭据及两种到期时间。响应失联、校验失败或持久化结果不明时保留执行记录，等待已验证的 OAuth 回调生效。原候选存储支持一组活跃 TikTok 绑定。 [代码提交](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/commit/b2e32219a1b6409067e52aff4317a13af945dd36) · [TikTok 官方续期规则](https://developers.tiktok.com/docs/en/oauth-refresh-a-user-access-token)
- 原站的健康检查返回 HTTP 200 和 `OK`。TikTok 状态返回 HTTP 200、已绑定及 `user.info.basic`，上传、直发及发布状态都是关闭。状态接口未返回国内运行版本或进程身份。国内预检运行 `38748827497` 记录了固定脚本的检查。候选代码仍待部署审批和实际部署回读。 [健康入口](https://www.xuanjunai.xin/healthz) · [TikTok 状态](https://www.xuanjunai.xin/integrations/tiktok/status) · [国内历史预检](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38748827497)

## 平台进度

公域平台来自原渠道蓝图。其余平台的账号状态以第 5 版原表和各官方控制台为依据。 [原渠道蓝图](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/a036c078202beb4db1e2185d3e17fe953036305c/docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md#L290)

| 平台 | 原账号及主体 | 注册、认证与授权 | 实测范围及下一步 |
| --- | --- | --- | --- |
| TikTok | 现有授权账号与开发者应用均已查到，应用列表含原组织应用 | 原站回读 `user.info.basic`。发布权限未开，账号认证详情待原表核对 | 原站接口读回绑定状态，候选续期通过合成测试。原应用保管人核对实际批准的发布方式，需遵守 TikTok 对内部团队管理工具的 Direct Post 限制。 [开发者控制台](https://developers.tiktok.com/portal/apps) · [内容发布规范](https://developers.tiktok.com/docs/en/content-sharing-guidelines) |
| 抖音 | 原正式网站应用「玄钧AI新」，控制台显示企业主体已做资质认证 | 行业角色显示未认证，创作者账号授权、实际投稿和数据能力待原应用核对 | 原候选已有刷新 access_token 的调用，合成请求与返回解析通过。候选发送表单编码，现行接口页列 `multipart/form-data`，真实兼容性和动态续期权限待核。原应用保管人查看内容能力和获准账号的授权范围。 [开放平台控制台](https://developer.open-douyin.com/console?type=4) · [刷新接口](https://open.douyin.com/platform/resource/docs/openapi/account-permission/refresh-access-token) · [投稿能力](https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/opensdk/content-management/share-and-publish-to-douyin) |
| 哔哩哔哩 | 原账号和应用待对账 | 注册、认证、投稿与数据授权待核 | 暂无实测链路。原账号保管人在开放平台定位既有应用及上传权限。 [开放平台](https://open.bilibili.com/) |
| 小红书 | 原账号和应用待对账 | 注册、认证、笔记发布与数据授权待核 | 暂无实测链路。原账号保管人核对既有应用可用授权范围。 [官方授权范围](https://openaccount.xiaohongshu.com/docs/scope) |
| YouTube | 原 Google 账号关联的项目频道待对账 | 频道归属、验证、上传和数据授权待核 | 暂无实测链路。原 Google 账号保管人确认既有频道，并从原通道提供授权范围。 [YouTube Studio](https://studio.youtube.com/) · [频道读取](https://developers.google.com/youtube/data/reference/rest/v3/channels/list) |
| Instagram | 原专业账号及主体待对账 | 专业账号类型、发布与数据授权待核 | 暂无实测链路。原账号保管人确认既有专业账号及应用的实际权限。 [官方发布流程](https://developers.facebook.com/documentation/instagram-platform/content-publishing) |
| Facebook Pages | 原主页及主体待对账 | 主页角色、应用审核、发布与数据授权待核 | 暂无实测链路。原主页管理员核对应用对既有主页的实际权限。 [Reels 发布](https://developers.facebook.com/documentation/video-api/guides/reels-publishing) |
| LinkedIn | 原组织主页与应用待对账 | 组织角色、应用审核、发帖和数据授权待核 | 暂无实测链路。原主页管理员核对组织角色及已授予的应用权限。 [组织授权](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-authorizations/organization-authorizations) |

原蓝图另列 Telegram 与企业微信两个授权沟通渠道。两者在本项目里的应用、可见范围及收件人授权待原渠道保管人核对。 [原渠道蓝图](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/a036c078202beb4db1e2185d3e17fe953036305c/docs/development/DEVELOPMENT_V27_ECOLOGY_V11_20261014.md#L330)

第 5 版账号台账的索引可以读取，原附件的访问仍需保管人给出可读引用。其余平台、账号归属和授权范围等到原表可读后对账。 [原台账索引](https://github.com/huhongchuan0422-creator/xuanjun-project-resources/blob/4a47dca662f29a355e84c8f953628dd938fc3065/ACCOUNT_REGISTER.md)

## 测试与回退

在 Linux 托管 Runner 执行，原候选 45 项回归和新增 15 项续期测试通过。样例凭据均为合成数据。已有前端 6 项状态测试也已在本地通过。 [Linux 作业](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/45627977002/job/139253172248)

```sh
python -B -m unittest discover -s tests -p test_pr122_oauth_candidate.py -v
python -B -m unittest discover -s tests -p test_pr122_tiktok_refresh_contract.py -v
node --test tests/test_pr122_tiktok_integration.mjs
```

代码回退在待集成分支执行 `git revert b2e32219a1b6409067e52aff4317a13af945dd36`。已在隔离 Git 索引反向应用，所得文件树等于候选基线。候选复用现有 SQLite 记录表。实际接线后若平台已轮换凭据，回退程序版本时保留当前数据库和续期记录。结果不明时由原账号持有人通过官方授权补回可用凭据。

## 首条待审内容

已制作《发布前，先过四关》的竖版视频、封面和发布文案。保留本地文件供审核，目标账号和发布时间待确认。国内运维需提供能绑定运行提交、服务入口和已授权账号的既有项目回执。发布回执及数据回读待正式授权后的端到端验收。

> 内容准备好之后，我会再过四道检查。素材有发布权吗？标题和画面说的是同一件事吗？发到哪个账号，谁能看到？排期有没有把时区写清楚？发出后再记下平台回执，留一个回看数据的入口。
