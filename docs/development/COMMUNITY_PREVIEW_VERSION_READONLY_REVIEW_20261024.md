# Issue76 原 UK 预览后继：最小只读版本核对候选

状态：PREPARED_FOR_ROOT_REVIEW / NOT_EXECUTED。本文不是部署、恢复、上传或现场执行许可。只沿原 iZd7oeikknn1z21sq6ji6zZ、原 Docker socket 和固定社区容器；不查询 P2/B5，不创建第二现场执行者，不启动服务或执行旧升级器。当前现场未知不等于未部署。

## 1 已有准确历史与原发布路径

- 原 Issue76 #6333101186：产品源码 `2330dd55c07f58d7f45a7c4510a9761d0d4735d6`；Docker image ID `sha256:0846f7cfc71d443095a6c5e3a59eabf5d2973eda90e29c831f335c163a2c8f32`；容器 ID `818fe0b0622c26c43685f61e79c6138ec0afce28adc7adb20aa56e68aac0b23c`。
- 历史状态 `PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING`；配置/数据复用，payments=false，角色/真实微信登录未验。
- 历史旧容器保留名 `xuanjun-community-preview-before-2330dd55`；历史升级前 image ID `sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30`，容器 `36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc`。
- 现场执行工具历史提交 `f5f6492ce827aa8cd9273f37bd9742190570f2f1`，工具 Tree `13020ebf8796972d9098cf65a85a6278908c0dbb`；原工具 `scripts/community_preview_upgrade.py` 固定旧 SHA/image，**不是可重跑的通用升级器**。
- 原阶段目录 `/opt/xuanjun-community-preview/roles-upgrade-2330dd55`；`attempt.json`、`resume-01/receipt.json` 是原回执引用。不能创建、覆盖或补造回执。
- 原发布路径是构建准确源码镜像 → 核准确 image/源包 → 原社区唯一 Writer 审核事务 → 保留当前容器与原配置数据 → 精确健康/入口核对及已审回滚。本文只准备第一步前的只读对账；新候选 image 尚未在本轮构建或加载，不把原 image ID 当新候选。

重要：Docker `.Id` 是 image ID；`RepoDigests` 才是仓库 digest 引用。离线加载镜像可能没有 RepoDigests，应如实输出 EMPTY/UNKNOWN，不把 `.Id` 冒充 registry digest。

## 2 供根独审的最小命令/读取白名单（尚未执行）

全部仅在原受保护现场入口、精确 hostname 及原既有权限下执行；每条子进程超时8秒、stdout/stderr合计上限64KiB，总时限60秒。超时、拒绝、未识别输出立即 HOLD，无重试、无恢复动作。不能输出 Docker 全量 inspect、完整 Env、Secret 文件内容、数据库行或原始错误。以下是 argv/模板审核材料，不是要求 Owner 现在执行的命令块。

| 目的 | 精确只读范围 | 允许回执 |
| --- | --- | --- |
| 当前容器 | `/usr/bin/docker --host unix:///var/run/docker.sock container inspect --format '{{json .Id}}\n{{json .Image}}\n{{json .State.Running}}\n{{json .Config.User}}' xuanjun-community-preview` | 当前 ID、image ID、运行布尔、UID:GID；不要求等于历史2330，否则先冻结实际后继 |
| 当前镜像 | 同一 Docker argv 的 `image inspect --format '{{json .Id}}\n{{json .RepoDigests}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'`；末参数仅取上一步核为 `sha256:[0-9a-f]{64}` 的当前 image ID，不接受请求方任意引用 | image ID、RepoDigests（可空）、OCI revision、原非root身份；不能 image pull/load |
| 回滚对象 | 与首条相同窄模板，只读固定 `xuanjun-community-preview-before-2330dd55` | ID/image/运行状态；不存在则 MISSING，不创建/改名/启动 |
| 原配置/数据引用 | 对固定 `/var/lib/xuanjun-community-preview/config`、`/var/lib/xuanjun-community-preview/data`、`/run/xuanjun-community-preview`、config 下 `host.json`/`center-keys.json`/`wechat.json` 做 lstat | 仅是否存在、类型、uid/gid/mode；不读密钥文件，不递归/读写DB，不创建快照 |
| 原路由绑定 | 只读 `/etc/nginx/community-preview.inc`、`/etc/nginx/conf.d/xuanjun-p2-owner.conf` 的 lstat 和有限字节 SHA256 | 仅固定路径元数据/摘要，不输出原文，不 nginx -t/reload，不修改任何vhost |
| 原事务回执 | 仅阶段目录下 `attempt.json` 和 `resume-01/receipt.json`；O_NOFOLLOW、根路径链及普通文件校验、最多64KiB | JSON仅投影 `state/source_sha/image_id/container_id/rollback_container/private_inputs_and_data/payments/role_acceptance/wechat_login_verified`；其他键值丢弃，缺失/错误固定 UNKNOWN，不能运行该目录内容 |
| 后端版本回读 | 仅 HTTPS GET `https://uk.wenwenwenyiyiyi.work/community-preview/community/health`，禁止重定向，10秒/4096字节/JSON | 仅 status/scope/production_acceptance/runtime_source_sha/version_source/observed_at；无版本字段记 UNKNOWN，不能用本地GITHUB_SHA补齐 |

挂载/启动绑定只能补固定布尔比较，不输出未知参数或Env：

- 原 Cmd 预期 `--plan /var/lib/xuanjun-community-preview/config/host.json --center-keys /var/lib/xuanjun-community-preview/config/center-keys.json --wechat-secret /var/lib/xuanjun-community-preview/config/wechat.json`；原 entrypoint 为 `python -B -m scripts.community_platform_host`。
- 原三 bind 映射为 config→同路径 RO、data→同路径 RW、`/run/xuanjun-community-preview`→同路径 RW。只在窄 Docker Go-template 中比较这些固定 Source/Destination/Type/RW 并输出 MATCH/HOLD，不输出全量 `.Mounts` 或未知路径。
- 若根需要实际命令封装，应将以上固定 argv、投影、timeout/kill/reap/大小限制集中冻结后独审一次；不得直接复用旧升级器的 main/resume/rollback，也不得把本表当现场已验结果。

## 3 版本/入口/依赖矩阵及一次性后续条件

| 项目 | 当前证据 | 后续准确要求 |
| --- | --- | --- |
| 125 原生候选 | `12516640b210032751f40f5d1d8edc715a622e1d` / Tree `2f7b850169f921278169192f51d15381935a4d10`；27文件及ZIP原摘要复核MATCH；SP40041063448/Preparation40041063447复用 | 本轮只改入口治理/证据门禁与材料；原生工程字节未变。实际预览再生成准确run SHA的receipt，不把125旧包称后继二维码 |
| 当前现场后端 | 2330成功历史已证明；当前容器/镜像/OCI/health版本本轮未读 | 先上述只读材料经根独审、原入口一次核当前后继，不假设仍2330也不假设未部署 |
| 前后端关系 | 125本版只支持远端IMAGE_BUILD_STAMP与本地frontend SHA EXACT_SOURCE_MATCH；未核现场 | 同版方可过门禁；异版必须另验明确版本对后另修兼容合同，不能自填SHA或沿用旧health PASS |
| 预览入口 | 原无场景首页引导，scene=null/query空；不是shop1模拟授权 | 真实业务入口继续沿已有商家门店二维码/原服务端scene授权；不创建主体/权限 |
| 默认分支登记 | 本轮最小main治理PR，只注册原路径，不搬业务长分支 | 根独审及正常分支保护后另决定合并，本轮不合并/dispatch |
| 手动test复用 | 原同SHA成功push Hosted run+实际test步骤成功+未过期同SHA source artifact元数据；不下载冒称字节校验 | 输入该准确run ID。当前checkout仍确定性重建源包并保留原manifest门禁；读取失败/错SHA/错workflow/错分支/过期/跳过test皆拒绝，不重跑旧业务“补绿” |
| 现场动作 | NOT_EXECUTED | 所有上述回执齐全后，Owner另核定一次原国内SDK preview；之后才是该SHA二维码/回执、真机、登录与审核发布验收 |

不新增密钥、权限、通道或工具安装；不运行 self-hosted、不启动容器、不改数据/路由、不执行真实进件/支付/材料上传。本材料不证明二维码已生成或发布完成。
