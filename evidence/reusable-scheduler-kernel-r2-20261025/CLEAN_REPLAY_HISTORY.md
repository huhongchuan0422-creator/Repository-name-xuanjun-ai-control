# 干净目录复跑历史

## 第一次归档：FAIL（保留）

- 归档 SHA256：`acdd91ded075232c64dd993770e01c6d1ea40039cb165779702cd8b96f1375b1`
- 结果：Supervisor 41/41 通过；后续 106 项中 3 项 Entry Review 用例失败。
- 精确原因：归档清单遗漏 `scripts/development_entry_intake.py`，其继续依赖 `native_syntax_intake.py` 与 `native_syntax_gate.py`；错误为 `ModuleNotFoundError: development_entry_intake`。
- 处置：该归档未交付；不改业务逻辑，只补齐真实运行依赖与 Manifest，再重新从空目录复跑。

## 第二次归档

待最终干净目录复跑后填写最终归档 SHA、大小与结果。
