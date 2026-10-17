# S07 依赖超时的离线续接

Owner 2026-10-17 00:52实机诊断：79份源码全部摘要一致，venv仅有pip23.3.1和setuptools68.0.0；官方PyPI下载10–16 KB/s，900秒时仍在下载idna。原安装与失败目录保留，不重跑原安装器。

本工具沿Owner长期/直接迁移授权#6219362469执行一个新的有限续接：韩国从官方PyPI下载原三个准确版本及其wheel依赖，校验wheel身份和成员路径、固定包名白名单、整包/逐wheel哈希，经固定国内ECDSA SSH通道传送，在既有隔离venv中使用--no-index --require-hashes安装。韩国已有环境只用其pip下载，不安装或改包。认证成功后才创建韩国续接目录；SSH连接保持900秒以覆盖下载等待。

国内只接受原DEPENDENCY_STEP_TIMEOUT失败、同一原始包、准确79文件清单与逐文件摘要、无占用该前缀的进程、原安装无成功回执、新续接目录不存在。源码不写、旧失败不改。新日志/缓存/回执置于/var/lib/xuanjun-pr99-s07-wheels-continuation-v1；韩国为/root/pr99-s07-wheels-continuation-v1。失败保留新旧现场，不自动重试或回滚。

安装后验证全部下载包的准确版本、pip check、三个第三方包导入、79份源码摘要，以及本次续接前后的Work首页/current及六个保护unit属性相等。不得追认为原安装失败时缺失的保护后快照。本批不读DB/凭据、不执行应用、不创建用户/unit，不启动服务或切反代。S07业务接续、S08–S10仍未完成。

新增本地9项测试通过；测试包含实际临时文件及合成wheel，身份/进程查询使用模型，不是Hosted或生产验收。原10项安装模型、S06/R2等已通过测试不重跑。执行结果以Owner新的root回执为准，成功终态DOMESTIC_S07_OFFLINE_DEPENDENCY_CONTINUATION_PASS。脚本SHA256：577d2e9a69186d6010dba2904e486de6617c657141e03d60eefb7975cb39a848。
