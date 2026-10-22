# 长期接线人工实施、验收与恢复交接包

状态：PREPARATION_COMPLETE_WITH_EXPLICIT_UNKNOWNS / NOT_ONE_CLICK / NOT_AUTHORIZED_TO_EXECUTE。
依据原PR17 #6333715145；仅整理原范围，不签发现场许可，不另建通道。
本包不是新的安装器，不修改0177d391源码；没有安装、回滚、浏览器恢复或秘密读取。
Owner已确认人工接续，G1已完成；下一批固定元数据核查见G23_METADATA_COMMAND.txt。不再要求重复决定。原写入准入和新增凭据/权限边界分别保留。

## 阅读顺序
1. INPUTS.json：每项已知证据、真实未知项、来源和对应阻断阶段。
2. STAGES.md：原流程实施顺序；只阻断依赖该缺项的阶段。
3. COMMAND_REFERENCE.txt：受限只读命令参考，不能串成一键安装。
4. ACCEPTANCE_RECOVERY.md：成功判据、停止规则、失败现场及安全续接。
5. EVIDENCE_INDEX.json：原权威记录、源码、CI和既有成功步骤。
6. source/：准确0177d391的30成员闭包及原Manifest原件，未改写。
7. PACKAGE_MANIFEST.json：本包全部成员的长度/模式/SHA。

## 已完成步骤不得重放
英国3.12.15 runtime、18依赖、原d866 release安装；国内DNS、HTTP01 bootstrap、已签发独立证书；已审源码及Hosted测试。原旧App/隧道/连接保留。
两份国内失败runtime归档保留，不续传、不删除、不重下；Certbot和系统Python不动。

## 当前不能诚实声称整链一键可执行
- 包来源/SourceRPM及已记录相关库补丁对应已由Owner回执补齐，见OWNER_RPM_EVIDENCE_20261022.json；原G1缺项限定关闭，不推为完整漏洞覆盖。
- authority专用身份、配置可读权限、已有/首次DB状态及准确生产配置绑定未实测完成。原/etc/xuanjun-cloud-oauth为root0700暂存根，不能直接假设非root authority可读其下配置，也不能擅自放宽该目录。
- 新GitHub OAuth App/client、平台新App/独立隧道、真实callback/resource、秘密保管引用和用户真实同意仍需正常获准创建/登记产生；本包不会造值或代替同意。
- 有效现场范围、操作人/时间/Attempt与当前冲突状态须沿已确认人工接续及原准入绑定；没有“自动获得五次/十次额度”的实现。

未知项不是已证源码缺陷；不得借人工交接绕过原观察限制、既有安全拒绝或独审。恢复浏览器并非人工执行的前置，但本包也不新设其他机器身份或访问通道。

## R2补记
Owner返回的6文件/4包结果完整无错误，来源及记录补丁对应已核清；不重复运行。原R1归档保持原SHA，本R2只更新交接证据/输入状态，不改0177源码。剩余UNKNOWN仍须按阶段处理，尚未安装依赖或启动服务。

## R3：G2/G3集中接续
G1完成与人工确认已同步。G2_ACQUISITION_AND_ACCEPTANCE.md提供准确30成员、18轮子取得/校验/独立venv与导入步骤；G3_ACCESS_AND_STATE.md集中权限与DB来源规则；B5_BINDINGS.json使用原Writer的实际catalog，不把372项当最终选择。G23_METADATA_COMMAND.txt只输出固定元数据，不读取配置/秘密/数据库正文、不更改现场。R2历史归档保留，不将其称安装包。
