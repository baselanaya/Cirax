// AudioWorklet processor — runs off the main thread for low-latency audio capture.
// Replaces the deprecated ScriptProcessor. Receives Float32 audio, converts to Int16 PCM,
// and sends to the main thread via MessagePort.

class CiraxAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._bufferSize = 4096; // accumulate before sending (matches old ScriptProcessor)
    this._buffer = new Float32Array(this._bufferSize);
    this._writeIndex = 0;
    // The page asks for a final flush before disconnecting us — otherwise up
    // to ~256ms of trailing speech (the last word of an utterance) is lost
    // at every capture stop.
    this.port.onmessage = (e) => {
      if (e.data && e.data.type === 'flush') {
        if (this._writeIndex > 0) this._flush();
        this.port.postMessage({ type: 'flushed' });
      }
    };
  }

  process(inputs, _outputs, _parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    // Downmix when the source is stereo (system-audio loopback commonly is):
    // reading only channel 0 silently drops anything panned right.
    const left = input[0];
    const right = input.length > 1 ? input[1] : null;
    const n = left.length;
    if (right) {
      for (let i = 0; i < n; i++) {
        this._buffer[this._writeIndex++] = (left[i] + right[i]) * 0.5;
        if (this._writeIndex >= this._bufferSize) this._flush();
      }
    } else {
      for (let i = 0; i < n; i++) {
        this._buffer[this._writeIndex++] = left[i];
        if (this._writeIndex >= this._bufferSize) this._flush();
      }
    }
    return true;
  }

  _flush() {
    // Convert Float32 [-1,1] to Int16 PCM
    const pcm = new Int16Array(this._writeIndex);
    for (let i = 0; i < this._writeIndex; i++) {
      const s = Math.max(-1, Math.min(1, this._buffer[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    this._buffer = new Float32Array(this._bufferSize);
    this._writeIndex = 0;
  }
}

registerProcessor('cirax-audio-processor', CiraxAudioProcessor);
