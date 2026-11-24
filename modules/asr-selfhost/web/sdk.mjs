/** Transport SDK: server inference remains on the existing self-hosted bridge.
 * No microphone access, third-party model dependencies, storage, or credential acquisition. */
export function createAsrClient({
  baseUrl = globalThis.location?.href,
  fetchImpl = globalThis.fetch,
  WebSocketImpl = globalThis.WebSocket,
} = {}) {
  const base = new URL(baseUrl);
  if (!["http:", "https:"].includes(base.protocol)) throw new TypeError("ASR base requires HTTP(S)");
  const statusUrl = new URL("./asr/status", base);
  const wsUrl = new URL("./asr/stream", base);
  wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";

  return {
    async status({signal} = {}) {
      const response = await fetchImpl(statusUrl, {
        credentials: "same-origin", redirect: "error", signal,
      });
      if (response.ok === false) throw new Error("ASR status unavailable");
      return response.json();
    },

    open({hotwords = [], onReady = () => {}, onResult = () => {}, onError = () => {}} = {}) {
      if (!Array.isArray(hotwords)) throw new TypeError("Expected a hotwords array");
      const ws = new WebSocketImpl(wsUrl);
      let state = "connecting";
      const release = () => {
        if (ws.readyState < 2) ws.close();
      };
      const report = (message) => {
        if (state === "closed") return;
        state = "closed";
        release();
        onError(new Error(message));
      };
      const send = (data) => {
        try { ws.send(data); return true; }
        catch { report("发送识别数据失败，已有文字仍可编辑。"); return false; }
      };

      ws.onopen = () => {
        if (state === "connecting") send(JSON.stringify({hotwords}));
      };
      ws.onclose = ws.onerror = () => report("识别连接已断开，已有文字仍可编辑。");
      ws.onmessage = ({data}) => {
        if (state === "closed") return;
        let event;
        try { event = JSON.parse(data); }
        catch { report("识别服务返回的数据无效。"); return; }
        if (event?.type === "ready" && state === "connecting") {
          state = "listening";
          onReady();
        } else if (event?.type === "result" && (state === "listening" || state === "stopping")) {
          if (typeof event.confirmed !== "string" || typeof event.draft !== "string" || typeof event.done !== "boolean") {
            report("识别服务返回的转写数据无效。");
            return;
          }
          if (event.done) { state = "closed"; release(); }
          onResult(event);
        } else if (event?.type === "error") {
          report(typeof event.message === "string" ? event.message : "本地识别未完成。");
        } else {
          report("识别服务返回的状态无效。");
        }
      };

      return {
        get state() { return state; },
        pushPCM(frame) {
          if (state !== "listening") return false;
          if (!(frame instanceof ArrayBuffer || ArrayBuffer.isView(frame)) || !frame.byteLength || frame.byteLength % 2) {
            throw new TypeError("Expected non-empty int16 PCM bytes");
          }
          return send(frame);
        },
        stop() {
          if (state !== "listening") return false;
          state = "stopping";
          return send("stop");
        },
        cancel() {
          if (state === "closed") return false;
          state = "closed";
          release();
          return true;
        },
      };
    },
  };
}
