import {createDraft} from "./core.mjs";
import {createAsrClient} from "./sdk.mjs";
const asr = createAsrClient();
const byId = (x) => document.getElementById(x);
const record = byId("record"), sample = byId("sample"), transcript = byId("transcript"), status = byId("status");
const machine = createDraft();
let session = null, available = false, sampleVersion = null, composing = false;

function render() {
  const {text, pending, appendable} = machine.view();
  if (transcript.value !== text && !composing) transcript.value = text;
  byId("count").textContent = `${[...transcript.value].length} 个字`;
  byId("candidate").textContent = pending;
  byId("suggestion").hidden = !pending;
  byId("append").hidden = !appendable;
  record.textContent = session?.phase === "recording" ? "■ 停止并定稿" : "● 开始录音";
  record.disabled = !available || sampleVersion !== null || (session != null && session.phase !== "recording");
  sample.disabled = session != null || sampleVersion !== null;
}
function say(message, phase = "可编辑") { status.textContent = message; byId("phase").textContent = phase; }
transcript.oncompositionstart = () => { composing = true; machine.edit(transcript.value); };
transcript.oncompositionend = () => { composing = false; machine.edit(transcript.value); render(); };
transcript.oninput = () => { machine.edit(transcript.value); render(); };
byId("append").onclick = () => { machine.appendSuggestion(); render(); transcript.focus(); };
byId("copy-suggestion").onclick = async () => {
  try { await navigator.clipboard.writeText(machine.view().pending); say("已复制识别结果，未改动文稿。"); }
  catch { say("可以选中识别结果后复制。"); }
};
byId("copy").onclick = async () => {
  try { await navigator.clipboard.writeText(transcript.value); say("已复制文稿。"); }
  catch { transcript.focus(); transcript.select(); say("请使用设备的复制命令。"); }
};
try {
  const data = await asr.status();
  available = data.available === true && !!navigator.mediaDevices?.getUserMedia && !!globalThis.AudioWorkletNode;
  byId("provider").textContent = available ? "点击后在自部署服务器上转写，不调用云识别 API。"
    : !data.available ? "自部署识别引擎尚未接通，可手输或试用示例。"
    : "此浏览器无法启用麦克风，请在支持录音的安全页面打开。";
} catch { byId("provider").textContent = "自部署识别引擎尚未接通，可手输或试用示例。"; }
render();

function stopCapture(s) { s.media?.getTracks().forEach((track) => track.stop()); }
function close(s, message, phase) {
  if (session !== s) return;
  session = null;
  stopCapture(s);
  s.context?.close().catch(() => {});
  s.transport?.cancel();
  machine.invalidate();
  say(message, phase); render();
}
record.onclick = async () => {
  if (session) {
    if (session.phase === "recording") {
      session.phase = "finalizing";
      say("正在等待最终识别结果…", "定稿中");
      session.pcm.port.postMessage("flush"); // Port FIFO sends the last PCM before stop.
      stopCapture(session);
      render();
    }
    return;
  }
  const s = {token: machine.begin(), phase: "connecting"};
  session = s; say("正在开启麦克风…"); render();
  try {
    s.media = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}});
    s.context = new AudioContext();
    await s.context.resume();
    await s.context.audioWorklet.addModule(new URL("./pcm-worklet.js", import.meta.url));
    s.pcm = new AudioWorkletNode(s.context, "mono-pcm");
    s.pcm.port.onmessage = ({data}) => {
      if (session !== s || !s.transport) return;
      if (data === "flushed") s.transport.stop();
      else s.transport.pushPCM(data);
    };
    s.transport = asr.open({
      hotwords: byId("hotwords").value.split(/[,，\n]/),
      onReady() {
        if (session !== s || s.phase !== "connecting") return;
        s.context.createMediaStreamSource(s.media).connect(s.pcm);
        s.pcm.connect(s.context.destination); // worklet emits silence, not a microphone monitor
        s.phase = "recording"; say("正在转写…", "实时初稿"); render();
      },
      onResult(e) {
        if (session !== s) return;
        machine.receive(s.token, e);
        if (e.done) {
          const message = !e.confirmed && !e.draft ? "没有听到可识别的内容，可重试或手动输入。"
            : e.draft ? "已保留文字，末段未确认，可手动核对。"
            : "识别已定稿，可手动修改。";
          close(s, message, e.draft ? "未完全定稿" : "可编辑");
        } else if (s.phase === "recording") {
          say(e.draft ? "正在转写；停顿后会校正。" : "这一段已定稿，可以继续说。", e.draft ? "实时初稿" : "已定稿");
        }
        render();
      },
      onError(err) { close(s, err.message, "未完成"); },
    });
  } catch { close(s, "未能开启麦克风或识别服务，仍可手动输入。", "未连接"); }
};

sample.onclick = () => {
  const version = sampleVersion = machine.begin();
  const frames = [
    {draft: "明天到示例"},
    {draft: "明天到示例三种，不是二中，下午三点。"},
    {confirmed: "明天到示例三中，不是二中，下午三点。", draft: "时间请"},
    {confirmed: "明天到示例三中，不是二中，下午三点。时间请不要改。", done: true},
  ];
  say("正在播放预设文字，不使用麦克风。", "流程示例"); render();
  frames.forEach((event, i) => setTimeout(() => {
    if (sampleVersion !== version) return;
    machine.receive(version, event);
    if (event.done) { sampleVersion = null; say("示例演示完毕，这不是实际录音或准确率测试。", "示例定稿"); }
    render();
  }, 350 + 700 * i));
};
