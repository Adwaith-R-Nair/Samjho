// Mic capture for the browser voice channel: downsamples whatever rate the device runs at to 16 kHz mono
// PCM16 and posts 20 ms chunks (320 samples) to the page.
class SamjhoMic extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / 16000; // input samples per output sample
    this.pos = 0;
    this.sum = 0;
    this.count = 0;
    this.out = new Int16Array(320);
    this.len = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      // Average the input samples that fall into each output sample (a cheap low-pass before decimating).
      this.sum += channel[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.step) {
        this.pos -= this.step;
        const v = Math.max(-1, Math.min(1, this.sum / this.count));
        this.out[this.len++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.sum = 0;
        this.count = 0;
        if (this.len === this.out.length) {
          this.port.postMessage(this.out.buffer, [this.out.buffer]);
          this.out = new Int16Array(320);
          this.len = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("samjho-mic", SamjhoMic);
