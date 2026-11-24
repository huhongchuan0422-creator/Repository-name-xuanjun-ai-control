# 自部署 CPU 引擎（Python / FunASR）

这条已实际运行的路线用 FunASR Python SDK + 官方 Paraformer 流式/离线权重 + FSMN-VAD，给现有共享 ASR 模块提供同样的 2pass WebSocket 协议。不是官方原生 C++/ONNX 安装，也不依赖付费云语音 API。此仓库没有权重和个人录音；独立的 CT-PUNC 自动标点尚未接入本 Python 验收路线。

## 一次导入，启动后断外网

先在获授权的机器上准备 64 位 Python 3.12、2+ 线程 CPU、约 8 GiB RAM、至少数 GB 磁盘。已实测的组件为 Python 3.12 + CPU PyTorch/TorchAudio 2.8.0 + FunASR 1.4.29。资源值不代表并发或性能承诺。

```sh
# 在仓库根目录。只创建局部虚拟环境，不改系统 Python。
python -m venv .venv-asr
. .venv-asr/bin/activate
# 以下为安装阶段的公开软件分发入口，不需要识别 API Key。
python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.8.0+cpu' 'torchaudio==2.8.0+cpu'
python -m pip install -r requirements.txt -r deploy/python-funasr/requirements-engine.txt
python deploy/python-funasr/fetch_models.py ./model-storage
# 运行阶段改用本地已验证的权重和依赖，确保不访问外网。
python deploy/python-funasr/local_funasr.py ./model-storage deploy/python-funasr/model-lock.json --port 10095
```

另开同机终端，激活相同 venv：

```sh
ASR_FUNASR_URL=ws://127.0.0.1:10095/ python -m uvicorn asr:app --host 127.0.0.1 --port 8011
```

业务端沿自己的 HTTPS 反代接 SDK，不直接对外暴露引擎端口。部署时仍应在系统或容器层限制外发网络；Python 引擎另外拒绝 Python socket 的非回环连接/DNS，不能把此防护当作系统级隔离。音频在内存中处理，网关和引擎不开启正文日志；停止调试实例不会改生产或自动重启。不限定总录音时长，VAD 依权重配置分段，长音频和并发尚需真实负载压测。

## 实音验收

```sh
node deploy/python-funasr/sdk_fixture_smoke.mjs /本地已授权的16k-16bit-单声道.wav http://127.0.0.1:8011/
```

脚本经真实 SDK/WSS 和本地模型，将同一份 WAV 拼接两次、中间加 2 秒静音，分别验证暂停后二遍定稿与停止后的尾句定稿。随后用 `accuracy.py` 对真实、已授权且有人工参考文本的测试集评估 CER、校名、数字、否定词和误写情况；重复音频两次出字相同也不等于对人工参考零错。当前一次性安装/验收只针对隔离环境，不代表对应引擎已部署到正式服务器。

`model-lock.json` 保存各权重发布者、精确仓库 revision、文件 SHA-256 和许可证据字段。官方 [流式版 Apache-2.0 快照](https://huggingface.co/funasr/paraformer-zh-streaming/tree/apache-2.0-20260804)包含 LICENSE 文本；离线模型、VAD 分别在精确发布者模型元数据中标注 Apache-2.0，原快照无单列 LICENSE。使用或分发时请保留原许可和权重来源；本仓库不把模型复制到源码、也不代用户接受其他条款。

隔离环境实测摘要见 `acceptance-public-fixture.json`。所用官方测试音频仅在验收机内读取，其原件 SHA 已固定，未提交到仓库。首版直接断流的两段重复音频有漏/增字差；调整原 PCM 准确的 VAD 前缘与停止后静音尾缘后，同一语料复测两句输出一致。不是实际项目精度结论。
