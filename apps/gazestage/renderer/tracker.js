// Face tracking with MediaPipe Face Landmarker (bundled in ./vendor, runs offline).
// MediaPipe runs in face-worker.js, off the page's thread; this side owns the camera and
// hands the worker one frame at a time. Emits one sample per processed frame:
//   { face: bool, yaw, pitch, ix, iy, blink, brightness, offCentre, size }
// yaw/pitch are head angles in radians; ix/iy are iris positions within the eye (0..1).

export class Tracker {
  constructor(video) {
    this.video = video;
    this.worker = null; this.loading = null; this.busy = false;
    this.running = false;
    this.lastTime = -1;
    this.onSample = () => {};
    this.canvas = document.createElement('canvas'); this.canvas.width = 32; this.canvas.height = 24;
    this.ctx2d = this.canvas.getContext('2d', { willReadFrequently: true });
    this.frame = 0; this.brightness = 0.5;
  }

  // Starts the face model in its worker. Resolves when it's ready; can be tried again after a failure.
  load() {
    if (this.loading) return this.loading;
    const worker = this.worker = new Worker(new URL('./face-worker.js', import.meta.url));
    this.loading = new Promise((resolve, reject) => {
      const fail = (message) => { worker.terminate(); this.worker = this.loading = null; reject(new Error(message)); };
      worker.onmessage = ({ data }) => {
        if (data.type === 'ready') resolve();
        else if (data.type === 'error') fail(data.message);
        else if (data.type === 'sample') { this.busy = false; this.onSample({ ...data.sample, brightness: this.brightness }); }
      };
      worker.onerror = (e) => { e.preventDefault(); fail(e.message || 'Face tracking couldn’t start'); };
    });
    worker.postMessage({ type: 'load' });
    return this.loading;
  }

  static async cameras() {
    return (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
  }

  async open(deviceId) {
    this.close();
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 }, ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'user' }) },
    });
    this.video.srcObject = this.stream;
    await this.video.play();
  }
  close() { this.stream?.getTracks().forEach(t => t.stop()); this.stream = null; }

  start() {
    if (this.running) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      // One frame at a time: while the worker is busy, newer frames are skipped, never queued.
      if (!this.busy && this.video.readyState >= 2 && this.video.currentTime !== this.lastTime) {
        this.lastTime = this.video.currentTime;
        this.process();
      }
      // requestVideoFrameCallback keeps latency lowest; fall back to animation frames.
      if (this.video.requestVideoFrameCallback) this.video.requestVideoFrameCallback(loop);
      else requestAnimationFrame(loop);
    };
    loop();
  }
  stop() { this.running = false; }

  // Hands the current frame to the worker; its sample comes back through onSample.
  async process() {
    if ((this.frame++ & 15) === 0) this.measureBrightness();
    this.busy = true;
    try {
      const frame = await createImageBitmap(this.video);
      this.worker.postMessage({ type: 'frame', frame, time: performance.now() }, [frame]);
    } catch { this.busy = false; }
  }

  measureBrightness() {
    try {
      this.ctx2d.drawImage(this.video, 0, 0, 32, 24);
      const d = this.ctx2d.getImageData(0, 0, 32, 24).data;
      let s = 0; for (let i = 0; i < d.length; i += 4) s += d[i] * 0.3 + d[i + 1] * 0.59 + d[i + 2] * 0.11;
      this.brightness = s / (d.length / 4) / 255;
    } catch {}
  }
}
