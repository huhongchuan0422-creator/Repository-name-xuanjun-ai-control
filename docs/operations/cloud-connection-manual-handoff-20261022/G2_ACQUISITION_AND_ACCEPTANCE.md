# G2准确取得、校验、安装与导入
## 本次已实际取得
原SOURCE=0177d391，原30成员及SOURCE_MANIFEST逐字节核对；18 wheels从官方https://pypi.org/simple按requirements.cp3116.lock的逐包哈希下载，当前Work环境退出0。总轮子6731878B，逐件文件名/size/SHA严格等于domestic-py3116-compatibility.json；不含sdist，不执行setup.py。完整输入归档见G2_PAYLOAD_RECEIPT.json，50普通成员=30源码+原Manifest+18轮子+输入索引。不是安装器/准入许可；国内交付、venv和实机导入尚未执行。R2仍只是文档/源码包。

## 取得方式与双端校验
优先交付本次已取得的完整归档，沿原获准私有渠道或Owner已确认的人工入口；本窗口没有可用服务器写/传输工具，不伪造已交付。固定归档整体SHA与receipt一致后，先检查成员类型/路径/重复及数量，拒绝链接/绝对路径/..，再在排他且全新root-owned0700保管目录展开；逐件核G2_PAYLOAD_MANIFEST长度/SHA和原SOURCE_MANIFEST。禁止tar直接写生产根、覆盖旧文件或借现有失败runtime目录。
另一正常方式是在国内原已批准官方下载范围内，使用已核系统3.11.6创建独立venv后以pip --isolated download --index-url https://pypi.org/simple --only-binary=:all: --require-hashes --no-deps -r requirements.cp3116.lock取得18轮子，再逐文件核已冻结filename/size/SHA；不切换镜像，不重新resolve或提高版本。网络失败保留下载现场并停止对应阶段。当前本地下载带cp311/abi3/none及manylinux2_34/2_28/2014/2_17目标参数，与原锁唯一哈希绑定。

## 目标状态核验后执行的原安装步骤（目前不是立即运行指令）
1. 使用G23固定元数据回执及原创建记录核目标归属。原admin经获准root安装，release/venv不授予服务写权限；任何已存在未知目标先对账，不覆盖。原完整流程排他要求保持。
2. 在最终路径/opt/xuanjun-cloud-oauth/venv-py3116直接运行 /usr/bin/python3.11 -I -B -m venv /opt/xuanjun-cloud-oauth/venv-py3116。venv不能先建于其他路径再rename；默认不启用system-site-packages。ensurepip失败停止，不借Certbot/pip系统环境或现场下载bootstrap脚本。
3. 用该venv的python -I -B -m pip --isolated install --no-index --find-links=本次已校验的固定保管目录/wheelhouse --only-binary=:all: --require-hashes --no-deps -r 本次固定release/deployment/cloud-connection/oauth/requirements.cp3116.lock。两个保管/release绝对路径须由本次实际交付回执绑定，未取得时不猜值。这是必须据实回填的交付参数，不是App/callback依赖。
4. python -I -B -m pip --isolated check；非0即停止，不修改锁补包。检查所有18发行版名称/版本与兼容JSON，venv base_prefix为系统3.11.6，prefix为独立目标、include-system-site-packages=false；导入authlib/flask/requests/waitress/cryptography/cffi/_ssl/_sqlite3，记录版本/导入文件来源及退出码。无需App、token、DB或启动HTTP。
5. 原run.py在本次root-owned不可写release校验30成员Manifest，不使用R3文档commit代替产品source。全部通过只记DEPENDENCIES_AND_IMPORT=PASS；服务UID沙箱、DB、HTTP、真实OAuth另验。

## 失败与回退
创建venv后失败保留该路径及执行ID/退出码/阶段，后续先核同事务并完成已批准恢复，不用--clear或删目录重试。成功阶段不重放。没有既有国内运行版本可虚构回滚；不改系统Python、Certbot、英国venv/source、DNS或证书。配置及App尚未生成不阻止上述离线准备，但阻止实际authority启动。
