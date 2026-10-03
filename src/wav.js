// Wrap raw Int16LE mono PCM in a WAV container so STT APIs accept it as a file.
function pcmToWav(pcm, sampleRate = 16000, channels = 1) {
  const dataSize = pcm.length;
  const byteRate = sampleRate * channels * 2;
  const blockAlign = channels * 2;
  const buf = Buffer.alloc(44 + dataSize);
  buf.write('RIFF', 0);
  buf.writeUInt32LE(36 + dataSize, 4);
  buf.write('WAVE', 8);
  buf.write('fmt ', 12);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);          // PCM
  buf.writeUInt16LE(channels, 22);
  buf.writeUInt32LE(sampleRate, 24);
  buf.writeUInt32LE(byteRate, 28);
  buf.writeUInt16LE(blockAlign, 32);
  buf.writeUInt16LE(16, 34);         // bits per sample
  buf.write('data', 36);
  buf.writeUInt32LE(dataSize, 40);
  pcm.copy(buf, 44);
  return buf;
}

// Rough loudness gate so we don't ship silence to the STT API.
function rms16(pcm) {
  if (pcm.length < 2) return 0;
  let sum = 0;
  const n = pcm.length / 2;
  for (let i = 0; i < pcm.length; i += 2) { const s = pcm.readInt16LE(i); sum += s * s; }
  return Math.sqrt(sum / n);
}

// RMS of the loudest sliceMs slice. Gating on a whole ~900ms window dilutes
// short speech with silence padding: 200ms of quiet talking inside mostly
// silence can average below the gate and get dropped whole.
function peakSliceRms16(pcm, sliceMs = 100, sampleRate = 16000) {
  if (pcm.length < 2) return 0;
  const sliceBytes = Math.max(2, Math.floor(sliceMs * sampleRate / 1000) * 2);
  let peak = 0;
  for (let off = 0; off < pcm.length; off += sliceBytes) {
    const slice = pcm.subarray(off, Math.min(off + sliceBytes, pcm.length));
    if (slice.length >= 2) peak = Math.max(peak, rms16(slice));
  }
  return peak;
}

module.exports = { pcmToWav, rms16, peakSliceRms16 };
