# 干净目录复跑历史

## 第一次归档：FAIL（保留）

- 归档 SHA256：`acdd91ded075232c64dd993770e01c6d1ea40039cb165779702cd8b96f1375b1`
- 结果：Supervisor 41/41 通过；后续 106 项中 3 项 Entry Review 用例失败。
- 精确原因：归档清单遗漏 `scripts/development_entry_intake.py`，其继续依赖 `native_syntax_intake.py` 与 `native_syntax_gate.py`；错误为 `ModuleNotFoundError: development_entry_intake`。
- 处置：该归档未交付；不改业务逻辑，只补齐真实运行依赖与 Manifest，再重新从空目录复跑。

## 第二次归档：PASS

- Manifest：31 个 payload 成员逐项 SHA256 通过。
- 支持的 Supervisor：41/41 PASS。
- Writer Fence、Entry Review、Runtime、Gateway、CLI：106/106 PASS。
- Node 界面组合测试：1/1 PASS。
- 合计：Python 147/147 PASS，Node 1/1 PASS。
- 最终归档自身 SHA 与大小由包外发送回执记录，避免包内容自引用导致摘要变化。
