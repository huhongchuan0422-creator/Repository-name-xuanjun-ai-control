# PR99 Owner直接生产启动入口

Owner于2026-10-19 00:29 CST取消独审及许可等待。本入口是该明确指令的普通实现，不签发独立审核或要求Owner提供新许可。

`owner_production_start.py start`沿用原生产STATE，借用原停止安装锁。首先核验实际最终材料，然后只退役原准确停止候选，独占创建正式单元、启动、检查健康；UNKNOWN保留而不重复操作。query-only只查原状态。

`/etc/xuanjun-pr99/domestic-final.start-inputs.json`是执行方由真实迁移结果生成的技术输入，包含准确源码/文件摘要、实际Fence/checkpoint/canonical assignment与专用账户，不是需要Owner签发的许可。当前这些现场结果尚未齐备；不创建假回执或用初步R2作为最终数据。

17项普通合成测试覆盖授权、原单元归属/冲突/退役、完整启动核心调用顺序及UNKNOWN保留；systemctl为mock，不是M99或现场生产启动。源码已发布，尚未安装到主机。

原受限40文件未修改或重发。本入口从已发布production_start.py（d645edc…）及stopped_transaction.py（99225aa…）派生，build_owner_start.py固定原摘要。
