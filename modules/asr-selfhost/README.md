# 实时语音转文字 · 自部署版 v0.2

**使用自己服务器上运行的 FunASR 两遍推理，不调用豆包、外部 API 或云端兜底，不需要识别 API Key，也没有按音频时长支付给识别供应商的费用。** 服务器算力、存储运维和所选模型许可仍有成本或条件。

浏览器实时输出初稿；停顿触发引擎二遍识别作句级定稿；继续说时保留前句，停止后将尾句发送给引擎定稿。手改始终保留，后到结果只供核对或明确追加，连接失败仍可手输。采用稳定的 UI 与宿主接口。

## 运行模块与验收环境

**已实测的路线：[Python / FunASR CPU 安装与验收](deploy/python-funasr/INSTALL.md)。**
在隔离环境中，将一份固定的公开官方 WAV 送入真实引擎，经 SDK 核对实时初稿、停顿后二遍定稿和停止后末句定稿。详见 [单样本验收摘要](deploy/python-funasr/acceptance-public-fixture.json)；不是地方口音、生产容量、真实宿主或普遍零错字的验收。该路线未接入独立 CT-PUNC 自动标点；以实际精确权重组合为准。

引擎绑定本机回环，语音识别不走外部 API 或备用服务。浏览器麦克风需 HTTPS 或 localhost；不新增应用登录、审批、白名单或录音总量限制，继承原宿主约束。连接与停止后等待定稿分别有 20 秒故障超时。模块本身不落盘语音或文本；部署时须同时核实实际引擎日志策略。

**C++ / ONNX 原生运行时是未验候选，并不是已验证的安装方式。** 可参考 [FunASR 官方原生协议及安装说明](https://github.com/modelscope/FunASR/blob/main/runtime/docs/SDK_advanced_guide_online.md)。选择该路线需另行锁定镜像、制品和许可，重新做真实语音验收。源码仓库不附带权重、二进制或录音，不代表可重新分发所引用的第三方模型；选定权重的精确版本、校验和与许可出处见 [模型清单](deploy/python-funasr/model-lock.json)。

### 兼容契约及实际验证

`GET /asr/status` 提供本地 WebSocket 握手可达性和 `funasr-local-2pass`，不表示已测试真实识别。 `WS /asr/stream` ：先发 `{"hotwords":[]}`，等 `ready`，再发二进制 PCM16LE（16 kHz 单声道），结束发文本 `stop`。状态结果：
`{type:"result",confirmed,draft,done,secondPassSeen}`。分句通过本地引擎 `2pass-offline` 纠偏；整流只有停止发送后收到末包确认才结束。不能把只有初稿的末包当定稿。宿主可用 `main_app.mount("/voice", create_app(...))`，小程序/原生 APP 可通过同契约替换浏览器录音层。

```sh
# 本地自动验收（部署手册以 requirements-dev.txt 补齐 httpx）
python -m unittest discover -s tests -v
node --test tests/*.test.mjs

# 原引擎和 ASR 模块启动后，跑一段获准、16kHz/16位/单声道 PCM WAV。
# 输出是文件中的录音文本，请仅在受授权环境查看和保留。
python smoke_audio.py /path/to/example.wav --hotword 示例三中

# 按 tests/corpus.json 的基准格式汇总真实预测后，再算 CER。
python accuracy.py tests/corpus.json predictions.json
```

可运行上述 Python 与 Node 测试。后端包括实际本地 WebSocket 连接到**协议替身**，以及倒序结果、停顿两句、代理禁用和重定向拒绝；前端用合成 UI 事件、缓冲 PCM 和模拟录音。因此已验证接口和控制流，这些自动化测试本身不包含真实识别；上面的单个公开 WAV 实测另计。地方口音准确率、目标硬件时延和正式宿主验收仍未完成。带合法固定权重在选定部署机上预热，再用真实地方口音、数字、否定、人名、低音量、静音和长句测错误率、关键字、省略/幻觉，以及浏览器/目标宿主完整链路。零错字是本地固定语料的验收目标，不代表可保证所有来音零误。

### 其他模块直接接 SDK

整套 ASR 服务只需在自有服务器部署一次，Web/H5 模块引入 `web/sdk.mjs`；没有 ASR 模型或登录逻辑被打包进客户模块。浏览器预览已经实际复用同一 SDK。示范宿主绑定在 `examples/host-input.mjs`，以相同目录结构保存，按模块方式引入。

```js
import {createAsrClient} from "./sdk.mjs";
const asr = createAsrClient({baseUrl: new URL("/voice/", location.origin)});
const {available} = await asr.status();
// 仅在用户发起录音时创建会话。onReady 之后才开始送 PCM。
const session = asr.open({hotwords: ["示例三中"],
  onReady: () => { /* 启动宿主已有录音 */ },
  onResult: (event) => { /* 以 event.confirmed + event.draft 更新本次语音草稿 */ },
  onError: (error) => { /* 保留已有文字，展示 error.message */ },
});
// 宿主每次拿到 PCM 16kHz / 单声道 / int16 小端：
session.pushPCM(pcmBytes); // ArrayBuffer 或 TypedArray，不接收 WAV 容器
// 用户停止，先冲刷录音器尾帧，再调用：
session.stop(); // 等最后的 done；主动无回执关闭可用 session.cancel()
```

`baseUrl` 用带尾斜杠的实际挂载路径。Web/H5 默认同源接入，WSS 与 HTTPS 同源凭证由现有宿主负责。小程序/原生 APP 如果没有标准 WebSocket 构造器，不声称此 JS 文件可直接运行，按相同协议适配宿主套接字与采集层。引入 SDK 不等于接管用户输入，建议复用 `web/core.mjs` 或优先保留宿主手改。起始、定稿、失败处理见设计和测试。
