# 官网开发中项目：展示目录接线（2026-11-04）

基线22dd09edbe770ed54f52749df297ec7f39fa2312；沿原showcase及官网发布器增量，不改登录、冻结模板、项目阶段或交付判定。安装协调：玄钧AI新。本文件不是安装、提权、凭据或生产变更授权。

## 一次性代码安装与日常内容管理

一次性由原协调核现场版本、草稿、lease/在途及授权，交装本版官网host模块、showcase脚本依赖与原nginx locations增量。不得覆盖未知现场修改。公共目录只读GET/HEAD：`/showcase/delivery/catalog.json`，对应`/var/lib/xuanjun-showcase/delivery/catalog.json`。state/history不暴露HTTP。没有新增匿名管理API、账户库、管理站或持久授权。

后续由原有受控操作员在**已安装代码目录**使用原登记入口；这些操作不构建网站、不切current、不重发静态页面：

```sh
python -m scripts.pr122_showcase_register display read
python -m scripts.pr122_showcase_register display put --expected-revision 0 --record deploy/pr122-showcase/shiliu-display-proposed.json
python -m scripts.pr122_showcase_register display unlist --expected-revision 1 --id shiliu-media
```

命令须使用现场已有受控root执行能力；本交付不配置sudo、远程执行或新权限。`put`可上架及更新同ID链接/说明；先read取得当前revision再写入，不照抄示例revision。恢复上架使用保留完整字段且listed=true的record。只有读命令不会创建目录。下架保留全部历史，不删除项目或业务资料。

管理源是私有state.json（0600），公开catalog为投影（0644）；加锁、目录/文件custody、revision比较并保留历史。revision冲突先查询，不盲重试。若收到PROJECTION_PENDING，写入可能已经提交：read查状态后，以查到的revision执行`display sync --expected-revision N`；sync不重复内容写入。未知投影改动拒绝覆盖，交原写入责任方对账。原审批、签名、有效期及原发布器/回滚机制均保留；展示登记不能提升私有源为PUBLIC或伪造任务验收。

## 官网读取与边界

复用原卡片、开发中/案例分类、模板和返回交互。打开页面、回到窗口或点击“刷新项目”时读取目录，更新链接/上下架无需重新构建；已打开页面可手动刷新。项目链接普通新标签打开，无身份转发或代理。外部项目不塞入冻结community-next模板iframe白名单。

同时读取原`/showcase/catalog.json`的已批准PUBLIC项目/页面；管理目录只描述获准公开的展示资料，不写phase、accepted、delivery、tenant或RBAC。匹配准确source_project_id才读取原阶段；无映射明确“项目阶段尚未接通”。目录获取失败不退回可能已经下架的旧列表，保留独立且明确标注的原社区模板演示。明确下架优先于原目录自动发现。原已验收且上线、有公开素材的案例条件保留，CI不等于交付。

没有新增条数、自动过期、域名白名单或逐次重复审批。链接需HTTPS或站内路径且不含凭据；原私有项目没有被扫描或默认公开。

## 首项拾陆与未接项

`shiliu-display-proposed.json`仅拟接入原件，未执行现场put。样例数据原型，不执行真实发布或互动。source_project_id=null，不猜原任务中心ID。Sites项目appgprj_6aea98b572a48191b94999389b39a1be配置public/active；本次普通HTTP请求403，但浏览器打开标题“拾陆传媒 · 工作台”。因此preview_access保留UNVERIFIED，不冒全部客户可达；公开访问由原协调确认。

| 准确缺项 | 当前责任/范围 |
|---|---|
| 现场代码/nginx增量安装、目录初始化、真实读取回执 | 玄钧AI新；先核现场授权与在途 |
| 拾陆公开访问回执、原任务项目ID及阶段来源映射 | 原协调、原任务中心责任方；本窗口不编造ID |
| 客户登录/统一身份与项目授权 | OpenClaw原登录职责；本版不写登录 |
| page/version/客户资产映射、真实评论保存回读 | 原客户中心接线责任方与官网集成；模板内存意见不冒后端保存 |
| 真实交付记录、精选页面/视频/说明公开素材授权 | 原项目Owner/交付责任方；未提供不冒完成案例 |

测试是隔离数据与原回归，不能代替生产目录、客户访问或业务验收。源码commit、同版制品与实际测试以本次交付回执为准。完整原交付目标、125成员客户中心合同和后继成果保留。


## 本次缺口修正与同版安装前置

此前机制包未收host.mjs、project-projection.mjs和pr122_delivery_host.py属实；现在机制Manifest同时收全6个宿主文件、9个冻结原件与适配器脚本，逐件绑定源码字节。它与原生官网候选是不同载荷：机制包用于源码/依赖交接，官网候选须由原发布器验证并交装，不可仅安装Python脚本就声称页面已更新。

原目录编译器输出的ACCEPTED不等于新适配器旧式delivery字段。本次读取原cases中的acceptance、snapshot_sha256、project_version及已发布页面制品引用；ACCEPTED不再被归为开发中。缺失验收绑定的ACCEPTED保留待核，不伪造交付。历史已验收快照和当前开发新版本可以各自保留。

独立`/delivery/cases.html`与宿主共享同一目录读取、投影和卡片渲染。公开演示链接许可与精选素材许可分开：受控record可选case_assets（kind/value/public_consent_ref），并用case_snapshot_sha256绑定准确原验收快照。素材种类description/image/video/link；不是默认公开全部页面。无精选素材授权或快照不符时，项目不会被重新塞回开发中，也不会生成公开案例。原记录不含这些可选字段仍可读写，历史保留。示例项目拾陆未提供实际验收和精选素材，不补造。

安装前由玄钧AI新核：现场HEAD/未知修改与lease/attempt；已安装showcase及nginx真实状态；原发布器准确源码/制品/Manifest/现行许可绑定；静态官网路由同版替换及外置目录GET读回。原showcase安装器是首次安装入口，会拒绝既有安装对象，不能拿本包盲目重跑；已有安装须沿原获准更新路径核差异。此处不签发许可、不新增安装通道，不替现场确认SENT/ACK。受控管理仍需原有操作员；本版没有客户登录或匿名管理写入。
