# GEO V4 Customer Integration Status — 2026-11-03

## Frozen source authority

Sites project: appgprj_6ae8cd2496188191a100ab382ac88e31
Sites version: 4
Sites prototype SHA: 842cc9707600aa3d47ad517ca67d14d0ffb31246
Main-repository handoff commit: 45b4f17da2fee562274ba4ee2cd43722031a148e
Source directory: handoff/geo-v4-customer

The four V4 implementation files are copied byte-for-byte into this directory and remain frozen:
- index.html SHA256 39ba7edef950d05c3ab32c626ff2eb19f00007e5a0e231316103a6ae1ea08456
- styles.css SHA256 90bb08cecbfc8c6033497dad09b6cb1c70a9d6a1c767910703ebf9868acf899a
- ecosystem.css SHA256 d9973bfc62cc3ee4facce90fa08b299c8701e1746059ccfc59358ea9e6cdb79a
- app.js SHA256 d6aa15803319ff60b7ec3b073f73eb85a65d2494d89a7cdf68070504700b6822

live.html differs from frozen index.html by one module script only:
../src/geo-v4-runtime.js

No V4 CSS, layout, frozen app code, navigation, wording, or functions are redrawn or deleted.

## Current real integration

Connected now:
- existing SaaS same-origin identity via /customer/center/api/me;
- project membership / role / tenant / customer context;
- cross-tenant rejection in geo runtime;
- existing GEO customer state model in src/geo.js;
- safe NOT_CONNECTED / UNKNOWN handling;
- no blind retry for unknown task outcomes.

Not found in the current repository as a customer HTTP contract:
- GEO entitlement purchase/activation;
- GEO Billing/Usage quota;
- GEO diagnosis/evidence service;
- GEO optimization task service;
- GEO version comment/confirmation service;
- GEO effect/result service;
- next-round task creation.

Backend/service owner for those missing contracts: UNKNOWN from current repository evidence. The separate backend-management responsibility must provide the authoritative service contract; this customer-side writer will not invent it.

## Frontend adapter seam

window.__XJ_GEO_CUSTOMER_SERVICE__ is only an internal frontend adapter seam, NOT a claimed backend endpoint.

Required read method:
snapshot({project_id, tenant_id, customer_id})

The adapter must map the authoritative backend response into the already-tested geo.js customer-state model. Until an authoritative adapter exists, the runtime reports NOT_CONNECTED, masks demo metrics as unavailable, and blocks demo mutations from creating false customer actions.

No secret, new credential, server access, production deployment, new billing system, second identity system, or second task system is created here.

## Visual verification limit

The frozen source is byte-identical to V4 and live.html adds only the runtime module. A new browser screenshot comparison is not claimed in this environment because Chromium navigation remains administratively blocked by ERR_BLOCKED_BY_ADMINISTRATOR and no bypass is used. Source/hash parity is verified; browser visual E2E remains NOT_VERIFIED.


## 2026-11-05催办核查

当前客户侧分支 HEAD 在本轮开工前仍为 `1d016ea3872b5e12cc60bd90730344fb2c585f11`，未发现 GEO 后继提交、GEO PR 或同一客户侧 Writer 接管记录。

仓库内已核到但**不能作为生产 GEO 客户接口**的现有能力：
- `scripts/community_saas_modules.py`：Stage5 离线模块目录/价格/权益模型；文件自身明确 OFFLINE product/contract model。
- `scripts/community_saas_phase2_http.py`：仅 127.0.0.1 的 offline/loopback HTTP。
- `scripts/task_supervisor_runtime.py`：任务监督运行时；明确不授予 authority、不创建 worker，也不是客户 GEO API。

因此当前真实后台合同仍未交付。客户侧所需最小权威合同已固化为：
`GEO_BACKEND_CONTRACT_REQUIRED.json`。

该契约要求统一后台/统一 SaaS 服务提供：
1. entitlement：模块是否启用、套餐、有效期；
2. Billing/Usage：额度、已用/剩余、权威来源；
3. diagnosis：诊断项、证据、来源与观察时间；
4. task：任务状态、步骤、UNKNOWN/重试语义；
5. versions：当前版本、评论与确认状态；
6. results：可比范围、指标、样本量及提升/持平/下降/数据不足；
7. next_round：继续优化资格、来源结果与新任务创建状态。

客户侧继续复用现有 `/customer/center/api/me` 身份/租户，不另建身份、计费、任务系统。后端/后台具体聊天窗口链接在当前仓库和本窗口可用上下文中仍无可核实记录，状态保持 `UNKNOWN`，不编造链接。

## V4视觉对照

冻结 V4 四文件仍按 SHA256 锁定；`live.html` 与冻结 `index.html` 的非业务差异仍只允许：
- fail-closed 首屏 guard；
- `geo-v4-runtime.js` 模块加载。

新回归 `geo-contract.test.js` 会再次锁定四文件 SHA 和 live/frozen 差异。真实浏览器截图对照仍受既有 `ERR_BLOCKED_BY_ADMINISTRATOR` 限制，不采用绕行手段，因此 Browser visual E2E 仍为 `NOT_VERIFIED`。
