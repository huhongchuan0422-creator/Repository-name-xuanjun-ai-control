# 专利公开合成示例：先托管，动态目录独立续接

授权Sentinel_0230d08e829081919a51ffa74154b26d，仅增加官网独立示例入口，不覆盖其他项目、不含真实技术资料、不改CSP或安全配置。原现场发布协调：玄钧AI新。本Writer仅交源码/增量和验证，不切current。

## 已接原件与兼容结论

patent-public-preview-exact.zip：24381B，SHA256 1307c68d639588a43aa3bde8b105e633bceb03a07db5d8cf07885ec74afb0d5f。
原source_commit cba85bf2fb89c03ca46cd6ce0c343b0cbfb0ec93属于专利示例来源，不在PR122业务仓冒查该commit。5文件原件保留在demos/pr122-patent-preview/original，内Manifest四文件尺寸/SHA均重算一致；原Manifest本身693B、SHA256 709f1f2aa4085597abc039bfe8656631720464dda71f4c295eddbb925ace4122。

原index.html有2处style属性，app.js模板有6处、共7种固定样式。仅将这些标签属性等值移为CSS类，原style.css字节整体保留并追加规则；Manifest逐个记录精确替换，可反向还原原HTML/JS。业务函数、文案、13环节和原响应式样式均复用。外部地址都是人工点击的官方资料链接；静态检查未发现fetch/XHR/WebSocket/Beacon/录音调用，正式浏览器验证另见同版报告。原本地草稿/意见仍只存浏览器，不冒登录后后台归档。

现行官网响应头有frame-ancestors none及X-Frame-Options DENY。原preview.html是iframe尺寸套壳，会被现行规则拒绝，本次不修改规则：默认直开index.html，PC/手机使用原响应式界面；套壳原文件保留证据但不作为本次托管入口。新增网页无内联脚本/style块及style属性，因此无需增加unsafe-inline、改现有CSP指令或手改hash白名单。

## 最小发布输入与步骤（原协调执行）

候选路径 /labs/patent-20261109/，仅3个资源：index.html、app.js、style.css。路径是拟发布位置，尚未宣称公网可达。

构建：python -m scripts.pr122_patent_public_preview --source demos/pr122-patent-preview/original --output <全新隔离目录>。
输出public/labs/patent-20261109/及PATENT_HOSTING_MANIFEST.json，已有输出拒绝覆盖。此工具不访问现场、不构造全站current、不发布、不改nginx。

1. 原协调先读现场current/版本、源码闭包、lease/attempt、接收回执，交准确旧字节/SHA。保留视频/labs/shiliu-20261104/、官网、社区、客户中心及所有后继；未知改动不能覆盖。
2. 在原发布流程的当前完整public闭包上仅追加这3文件，目标若已存在先对账；不能使用旧1303基础包全量替换，不能直接把3文件增量当完整站重算CSP或切current。
3. 原发布器compose/prepare→核完整Manifest/差异→release→current→HTTPS及限定恢复。本站点新增0项内联hash，其他原CSP元数据和安全头必须保持。原严格1303/1256合同不能把新增3文件假装成旧包：需先读现行升级合同；若仍固定旧合同，由本Writer依同一原入口补准确增量绑定，安装方不得代改源码、泛接受或绕legacy。当前未取得现场闭包/现行升级合同，所以本包不是已准入完整生产release。
4. 客户入口以官网域名该独立目录的index.html为准，核HTML/CSS/JS 200、桌面/手机、13环节及现行CSP无拒绝，再交真实SENT/ACK/HTTPS回执。失败先query原attempt，不盲重试，不动其他项目。

无需等待统一登录、客户私有权限、任务中心阶段或动态目录完成，即可按现行授权单独托管这个合成示例。以上未接业务不冒通过。

## 动态管理实际状态与一次接线

本次只读实测：/showcase/delivery/catalog.json 404；/showcase/catalog.json 404；/customer/center/api/delivery_projects 404；原/labs/shiliu-20261104/ 200。这说明这些线上读取端点尚未提供，不证明服务/进程已停止。

原源端入口：python -m scripts.pr122_showcase_register display read/put/unlist/sync；由原受控root操作员运行，带expected-revision，不是匿名HTTP写接口。源state/history在/var/lib/xuanjun-showcase/delivery/，读端GET /showcase/delivery/catalog.json使用原精确nginx alias。一次接线时核原代码、读路由和前端host，沿既有升级完成；之后目录上/下架、更新链接只改元数据，不构建或重发官网。公众读目录不依赖客户登录；管理写依赖原受控操作身份；私有项目/持久评论另依赖OpenClaw正式会话/CSRF/FULL及原签名项目版本来源，不能把它们当公开示例托管的前置。

专利托管HTTPS核成后，再通过原display put将既有patent-workbench记录的preview_url更新为已证官网地址，沿同ID更新、不新增重复卡；先读现行revision与记录，保留其他字段/历史。候选登记原chatgpt.site地址不能冒新官网地址已发布。静态托管和动态管理分别交回执，前者不冒后者完成。
