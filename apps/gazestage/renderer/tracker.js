// Face tracking with MediaPipe Face Landmarker (bundled in ./vendor, runs offline).
// Emits one sample per camera frame:
//   { face: bool, yaw, pitch, ix, iy, blink, brightness, centred }
// yaw/pitch are head angles in radians; ix/iy are iris positions within the eye (0..1).

const VENDOR = new URL('./vendor/', import.meta.url).href;

export class Tracker {
  constructor(video) {
    this.video = video;
    this.landmarker = null;
    this.running = false;
    this.lastTime = -1;
    this.onSample = () => {};
    this.canvas = document.createElement('canvas'); this.canvas.width = 32; this.canvas.height = 24;
    this.ctx2d = this.canvas.getContext('2d', { willReadFrequently: true });
    this.frame = 0; this.brightness = 0.5;
  }

  async load() {
    if (this.landmarker) return;
    const vision = await import(VENDOR + 'vision_bundle.mjs');
    const files = await vision.FilesetResolver.forVisionTasks(VENDOR + 'wasm');
    const opts = (delegate) => ({
      baseOptions: { modelAssetPath: VENDOR + 'face_landmarker.task', delegate },
      runningMode: 'VIDEO', numFaces: 1,
      outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
    });
    try { this.landmarker = await vision.FaceLandmarker.createFromOptions(files, opts('GPU')); }
    catch { this.landmarker = await vision.FaceLandmarker.createFromOptions(files, opts('CPU')); }
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
      if (this.video.readyState >= 2 && this.video.currentTime !== this.lastTime) {
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

  process() {
    if ((this.frame++ & 15) === 0) this.measureBrightness();
    const r = this.landmarker.detectForVideo(this.video, performance.now());
    if (!r.faceLandmarks?.length) { this.onSample({ face: false, brightness: this.brightness }); return; }
    const L = r.faceLandmarks[0];
    const m = r.facialTransformationMatrixes[0].data;   // 4x4, column-major
    const yaw = Math.atan2(m[8], m[10]);
    const pitch = Math.asin(Math.max(-1, Math.min(1, -m[9])));
    const eye = (iris, outer, inner, top, bottom) => {
      const w = L[inner].x - L[outer].x, h = L[bottom].y - L[top].y;
      return [(L[iris].x - L[outer].x) / (w || 1e-3), (L[iris].y - L[top].y) / (h || 1e-3)];
    };
    const a = eye(468, 33, 133, 159, 145), b = eye(473, 263, 362, 386, 374);
    const bs = Object.fromEntries((r.faceBlendshapes[0]?.categories || []).map(c => [c.categoryName, c.score]));
    const nose = L[1];
    this.onSample({
      face: true, yaw, pitch,
      ix: (a[0] + (1 - b[0])) / 2, iy: (a[1] + b[1]) / 2,
      blink: Math.min(bs.eyeBlinkLeft || 0, bs.eyeBlinkRight || 0),
      brightness: this.brightness,
      // How centred the face is in the camera frame: 0 = centred, 1 = at the edge.
      offCentre: Math.max(Math.abs(nose.x - 0.5), Math.abs(nose.y - 0.5)) * 2,
      // Face width as a fraction of the frame: too small = too far away.
      size: Math.abs(L[454].x - L[234].x),
    });
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
