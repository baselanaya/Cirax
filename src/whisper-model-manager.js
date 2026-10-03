const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { once } = require('events');
const { finished } = require('stream/promises');
const { WHISPER_MODELS } = require('./whisper-model-catalog');

const MODEL_DIRECTORY_NAME = 'whisper-models';
const PROGRESS_INTERVAL_MS = 150;

class WhisperModelManager {
  /**
   * Manage verified model artifacts under Electron's userData directory.
   * Dependencies are injectable so downloads can be tested without a network.
   */
  constructor({ userDataPath, fetchImpl = global.fetch, now = Date.now, models = WHISPER_MODELS } = {}) {
    if (!userDataPath) throw new Error('WhisperModelManager requires a userDataPath.');
    if (typeof fetchImpl !== 'function') throw new Error('A Fetch-compatible implementation is required.');

    this.modelDirectory = path.join(userDataPath, MODEL_DIRECTORY_NAME);
    this.fetchImpl = fetchImpl;
    this.now = now;
    this.models = Object.freeze(Array.from(models));
    this.modelById = new Map(this.models.map((model) => [model.id, model]));
    this.activeDownload = null;
  }

  getModelPath(modelId) {
    return path.join(this.modelDirectory, this._requireModel(modelId).filename);
  }

  getPartialPath(modelId) {
    return `${this.getModelPath(modelId)}.part`;
  }

  // A successful full verification writes this sidecar so later sessions
  // skip the multi-GB re-hash (capture start paid ~a second per model
  // otherwise). Trusted only when the file size still matches.
  getVerifiedPath(modelId) {
    return `${this.getModelPath(modelId)}.verified`;
  }

  async _isVerifiedFast(modelId) {
    const model = this.modelById.get(modelId);
    if (!model) return false;
    try {
      const [size, marker] = await Promise.all([
        this._getFileSize(this.getModelPath(modelId)),
        fs.promises.readFile(this.getVerifiedPath(modelId), 'utf8')
      ]);
      return size === model.bytes && marker.trim() === model.sha256;
    } catch {
      return false;
    }
  }

  async _markVerified(modelId) {
    const model = this.modelById.get(modelId);
    if (!model) return;
    try {
      await fs.promises.writeFile(this.getVerifiedPath(modelId), model.sha256, 'utf8');
    } catch { /* best-effort speedup only */ }
  }

  async listModels() {
    await fs.promises.mkdir(this.modelDirectory, { recursive: true });
    return Promise.all(this.models.map(async (model) => {
      const [installedBytes, partialBytes] = await Promise.all([
        this._getFileSize(this.getModelPath(model.id)),
        this._getFileSize(this.getPartialPath(model.id))
      ]);
      return {
        ...model,
        installed: installedBytes === model.bytes,
        installedBytes,
        partialBytes,
        downloading: this.activeDownload?.modelId === model.id
      };
    }));
  }

  /**
   * Download one model at a time. A valid partial file is resumed with Range;
   * completed bytes remain on cancellation so the next attempt can continue.
   */
  async download(modelId, onProgress = () => {}) {
    const model = this._requireModel(modelId);
    if (this.activeDownload) {
      throw new Error(`Already downloading ${this.activeDownload.modelId}.`);
    }

    await fs.promises.mkdir(this.modelDirectory, { recursive: true });
    const targetPath = this.getModelPath(modelId);
    const partialPath = this.getPartialPath(modelId);
    const targetBytes = await this._getFileSize(targetPath);
    if (targetBytes === model.bytes) {
      if (await this._isVerifiedFast(modelId)) return { modelId, installed: true, resumed: false };
      try {
        await this._verifyArtifact(targetPath, model);
        await this._markVerified(modelId);
        return { modelId, installed: true, resumed: false };
      } catch {
        await fs.promises.rm(targetPath, { force: true });
      }
    } else {
      await fs.promises.rm(targetPath, { force: true });
    }

    let partialBytes = await this._getFileSize(partialPath);
    if (partialBytes > model.bytes) {
      await fs.promises.truncate(partialPath, 0);
      partialBytes = 0;
    }
    if (partialBytes === model.bytes) {
      try {
        await this._verifyArtifact(partialPath, model);
        await fs.promises.rename(partialPath, targetPath);
        return { modelId, installed: true, resumed: true };
      } catch {
        await fs.promises.truncate(partialPath, 0);
        partialBytes = 0;
      }
    }

    const abortController = new AbortController();
    this.activeDownload = { modelId, abortController };
    const headers = partialBytes > 0 ? { Range: `bytes=${partialBytes}-` } : {};

    try {
      const response = await this.fetchImpl(model.url, {
        headers,
        redirect: 'follow',
        signal: abortController.signal
      });
      // A 416 with a within-range local .part means the server's file no
      // longer matches our offset — every retry would fail identically.
      // Restart from byte zero instead of wedging until manual cleanup.
      if (response.status === 416 && partialBytes > 0) {
        await fs.promises.rm(partialPath, { force: true });
        partialBytes = 0;
        const restarted = await this.fetchImpl(model.url, { redirect: 'follow', signal: abortController.signal });
        if (!restarted.ok) throw new Error(`Model download failed with HTTP ${restarted.status}.`);
        await this._writeResponseBody(restarted, partialPath, model, 0, false, onProgress);
        await this._verifyArtifact(partialPath, model);
        await fs.promises.rename(partialPath, targetPath);
        await this._markVerified(modelId);
        onProgress({ modelId, receivedBytes: model.bytes, totalBytes: model.bytes, percent: 100 });
        return { modelId, installed: true, resumed: false };
      }
      const shouldAppend = partialBytes > 0 && response.status === 206;
      if (!response.ok) {
        throw new Error(`Model download failed with HTTP ${response.status}.`);
      }

      if (!shouldAppend) partialBytes = 0;
      await this._writeResponseBody(response, partialPath, model, partialBytes, shouldAppend, onProgress);
      await this._verifyArtifact(partialPath, model);
      await fs.promises.rename(partialPath, targetPath);
      await this._markVerified(modelId);
      onProgress({ modelId, receivedBytes: model.bytes, totalBytes: model.bytes, percent: 100 });
      return { modelId, installed: true, resumed: shouldAppend };
    } catch (error) {
      if (abortController.signal.aborted) {
        const cancelledError = new Error(`Download cancelled for ${modelId}.`);
        cancelledError.code = 'DOWNLOAD_CANCELLED';
        throw cancelledError;
      }
      if (error.code === 'ARTIFACT_CHECKSUM_MISMATCH' || error.code === 'ARTIFACT_SIZE_MISMATCH') {
        await fs.promises.rm(partialPath, { force: true });
      }
      throw error;
    } finally {
      this.activeDownload = null;
    }
  }

  cancelDownload(modelId) {
    if (!this.activeDownload || this.activeDownload.modelId !== modelId) return false;
    this.activeDownload.abortController.abort();
    return true;
  }

  async deleteModel(modelId) {
    this._requireModel(modelId);
    if (this.activeDownload?.modelId === modelId) {
      throw new Error('Cancel the active download before deleting this model.');
    }
    await Promise.all([
      fs.promises.rm(this.getModelPath(modelId), { force: true }),
      fs.promises.rm(this.getPartialPath(modelId), { force: true }),
      fs.promises.rm(this.getVerifiedPath(modelId), { force: true })
    ]);
    return { modelId, installed: false };
  }

  async importModel(modelId, sourcePath) {
    const model = this._requireModel(modelId);
    if (!sourcePath) throw new Error('No model file was selected.');
    if (this.activeDownload) throw new Error('Wait for the active model download to finish.');

    await fs.promises.mkdir(this.modelDirectory, { recursive: true });
    const targetPath = this.getModelPath(modelId);
    const importingPath = `${targetPath}.importing`;
    await fs.promises.copyFile(sourcePath, importingPath);
    try {
      await this._verifyArtifact(importingPath, model);
      // Rename first, delete nothing up front: the old flow (rm target →
      // rename) destroyed BOTH copies when the rename failed (EBUSY/EPERM
      // from antivirus is common on Windows) — forcing a multi-GB re-download.
      const backupPath = `${targetPath}.old`;
      let hadOld = false;
      try {
        await fs.promises.rename(targetPath, backupPath);
        hadOld = true;
      } catch { /* no previous install */ }
      try {
        await fs.promises.rename(importingPath, targetPath);
      } catch (renameError) {
        if (hadOld) await fs.promises.rename(backupPath, targetPath).catch(() => {});
        throw renameError;
      }
      if (hadOld) await fs.promises.rm(backupPath, { force: true });
      await this._markVerified(modelId);
      return { modelId, installed: true };
    } catch (error) {
      // The verified copy at importingPath is GOOD — only remove it for
      // verification failures, never after a rename hiccup.
      await fs.promises.rm(importingPath, { force: true });
      throw error;
    }
  }

  async verifyInstalledModel(modelId) {
    const model = this._requireModel(modelId);
    const modelPath = this.getModelPath(modelId);
    await fs.promises.access(modelPath, fs.constants.R_OK);
    if (await this._isVerifiedFast(modelId)) return modelPath;
    await this._verifyArtifact(modelPath, model);
    await this._markVerified(modelId);
    return modelPath;
  }

  // Time O(n), space O(1): audio models can be several GB, so hash by stream.
  async _sha256(filePath) {
    const hash = crypto.createHash('sha256');
    const input = fs.createReadStream(filePath);
    for await (const chunk of input) hash.update(chunk);
    return hash.digest('hex');
  }

  async _verifyArtifact(filePath, model) {
    const bytes = await this._getFileSize(filePath);
    if (bytes !== model.bytes) {
      const error = new Error(`Model size mismatch for ${model.id}: expected ${model.bytes}, received ${bytes}.`);
      error.code = 'ARTIFACT_SIZE_MISMATCH';
      throw error;
    }
    const sha256 = await this._sha256(filePath);
    if (sha256 !== model.sha256) {
      const error = new Error(`Model checksum mismatch for ${model.id}.`);
      error.code = 'ARTIFACT_CHECKSUM_MISMATCH';
      throw error;
    }
  }

  async _getFileSize(filePath) {
    try {
      return (await fs.promises.stat(filePath)).size;
    } catch (error) {
      if (error.code === 'ENOENT') return 0;
      throw error;
    }
  }

  _requireModel(modelId) {
    const model = this.modelById.get(modelId);
    if (!model) throw new Error(`Unsupported Whisper model: ${modelId}`);
    return model;
  }

  async _writeResponseBody(response, partialPath, model, startingBytes, append, onProgress) {
    if (!response.body) throw new Error('Model download returned an empty body.');
    const output = fs.createWriteStream(partialPath, { flags: append ? 'a' : 'w' });
    const outputFinished = finished(output);
    let receivedBytes = startingBytes;
    let lastProgressAt = 0;

    try {
      for await (const chunk of response.body) {
        const buffer = Buffer.from(chunk);
        receivedBytes += buffer.length;
        if (receivedBytes > model.bytes) {
          throw new Error(`Model download exceeded the expected size for ${model.id}.`);
        }
        if (!output.write(buffer)) await once(output, 'drain');

        const progressTime = this.now();
        if (progressTime - lastProgressAt >= PROGRESS_INTERVAL_MS) {
          lastProgressAt = progressTime;
          onProgress({
            modelId: model.id,
            receivedBytes,
            totalBytes: model.bytes,
            percent: Math.floor((receivedBytes / model.bytes) * 100)
          });
        }
      }
    } finally {
      output.end();
      await outputFinished;
    }
  }
}

module.exports = { WhisperModelManager, MODEL_DIRECTORY_NAME };
