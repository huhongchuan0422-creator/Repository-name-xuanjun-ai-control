/* Track setting can be 44.1/48 kHz even when the UI asks for 16 kHz.
 * Integrate source samples over each output sample interval for streaming
 * box-filter downsampling. Never reset phase at a render-quantum boundary. */
class MonoPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.window = Math.round(sampleRate);
    this.remaining = this.window;
    this.sum = 0;
    this.reset();
    this.stopping = false;
    this.port.onmessage = ({data}) => {
      if (data === "flush") {
        this.stopping = true;
        const n = this.window - this.remaining;
        if (n > 0) this.push(this.sum / n);
        this.emit();
        this.port.postMessage("flushed");
      }
    };
  }
  reset() { this.buffer = new ArrayBuffer(5120); this.out = new DataView(this.buffer); this.offset = 0; }
  emit() {
    if (this.offset) {
      const bytes = this.offset === this.buffer.byteLength ? this.buffer : this.buffer.slice(0, this.offset);
      this.port.postMessage(bytes, [bytes]);
      this.reset();
    }
  }
  push(v) {
    v = Math.max(-1, Math.min(1, v));
    this.out.setInt16(this.offset, v < 0 ? Math.round(v * 32768) : Math.round(v * 32767), true);
    this.offset += 2;
    if (this.offset === this.buffer.byteLength) this.emit();
  }
  process(inputs) {
    if (this.stopping) return false;
    const tracks = inputs[0] || [];
    if (!tracks.length) return true;
    for (let i = 0; i < tracks[0].length; i++) {
      const v = tracks.reduce((a, t) => a + t[i], 0) / tracks.length;
      let fraction = 16000;
      while (fraction > 0) {
        const used = Math.min(fraction, this.remaining);
        this.remaining -= used; fraction -= used; this.sum += v * used;
        if (this.remaining === 0) {
          this.push(this.sum / this.window);
          this.remaining = this.window;
          this.sum = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("mono-pcm", MonoPCM);
