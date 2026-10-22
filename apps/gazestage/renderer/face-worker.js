// Face tracking in its own thread. Loading MediaPipe and reading each frame can take seconds
// on a computer without a fast graphics chip; here it never freezes the window or holds up
// answers to other Limitless Sound apps. A classic worker (not a module one), because MediaPipe
// loads its WebAssembly with importScripts.
//   in:  { type: 'load', remembered: 'GPU' | 'CPU' | '' }, then { type: 'frame', frame: ImageBitmap, time }
//   out: { type: 'ready', delegate, why, remember? } or { type: 'error', message },
//        then { type: 'sample', sample } per frame, and { type: 'delegate', ... } if it switches
//   remember: the delegate for the page to keep for next time ('' to forget it); left out to keep what it has.
'use strict';
const VENDOR = new URL('vendor/', self.location.href).href;
let vision = null, files = null, landmarker = null, failing = false;
let trial = null;   // while the graphics chip proves it's faster than the CPU here

const make = (delegate) => vision.FaceLandmarker.createFromOptions(files, {
  baseOptions: { modelAssetPath: VENDOR + 'face_landmarker.task', delegate },
  runningMode: 'VIDEO', numFaces: 1,
  outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
});

// The graphics renderer's name when it's software (or there's no WebGL 2), where MediaPipe's GPU
// delegate is many times slower than its CPU one; '' for a real graphics chip.
function softwareGraphics() {
  try {
    const gl = new OffscreenCanvas(1, 1).getContext('webgl2');
    if (!gl) return 'no WebGL 2';
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    const name = String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return /swiftshader|llvmpipe|softpipe|software|basic render/i.test(name) ? name : '';
  } catch { return 'no WebGL'; }
}

// Starts a delegate and reads one blank frame with it, so its first-frame setup (seconds, on a
// slow graphics chip) is done while the camera starts. Returns it and how long that frame took.
async function start(delegate) {
  const next = await make(delegate);
  const t = performance.now();
  next.detectForVideo(new ImageData(64, 64), 0);
  return [next, Math.round(performance.now() - t)];
}

// Picks the delegate: the CPU straight away with software graphics; otherwise the one that was
// faster here before; otherwise the graphics chip, on trial: its first frame must take under
// 1.5 s (then see judge). If the choice won't start, the other one, and the next start checks again.
async function load(remembered) {
  vision = await import(VENDOR + 'vision_bundle.mjs');
  files = await vision.FilesetResolver.forVisionTasks(VENDOR + 'wasm');
  const soft = softwareGraphics();
  const choice = soft ? { delegate: 'CPU', why: `software graphics (${soft})` }
    : remembered ? { delegate: remembered, why: 'the faster one on this computer before' }
      : { delegate: 'GPU', why: 'graphics chip, checking it’s faster than the CPU' };
  let first;
  try { [landmarker, first] = await start(choice.delegate); }
  catch (e) {
    const other = choice.delegate === 'GPU' ? 'CPU' : 'GPU';
    [landmarker] = await start(other);
    return { delegate: other, why: `${choice.delegate} didn’t start (${e?.message || e})`, remember: remembered ? '' : other };
  }
  if (soft || remembered) return choice;
  if (first > 1500) {
    landmarker.close(); [landmarker] = await start('CPU');
    return { delegate: 'CPU', why: `the graphics chip took ${first} ms for its first frame`, remember: 'CPU' };
  }
  trial = { gpu: [] };
  return choice;
}

// The rest of the graphics chip's trial: its next frames must take no more than twice what the
// CPU needs. Otherwise GazeStage switches to the CPU, once. Either way the page remembers the winner.
async function judge(ms, frame, time) {
  if (trial.gpu.length < 8) trial.gpu.push(ms);
  else if (!trial.cpu) { [trial.cpu] = await start('CPU'); trial.cpuMs = []; }
  else {
    const t = performance.now(); trial.cpu.detectForVideo(frame, time); trial.cpuMs.push(Math.round(performance.now() - t));
    if (trial.cpuMs.length < 4) return;
    const gpu = median(trial.gpu), cpu = median(trial.cpuMs);
    const why = `graphics chip ${gpu} ms a frame, CPU ${cpu} ms`;
    if (gpu > 2 * cpu) decide('CPU', why, trial.cpu);
    else { trial.cpu.close(); decide('GPU', why); }
  }
}
const median = (a) => [...a].sort((x, y) => x - y)[a.length >> 1];
function decide(delegate, why, next) {
  if (next) { landmarker.close(); landmarker = next; }
  trial = null;
  postMessage({ type: 'delegate', delegate, why, remember: delegate });
}

// One sample from MediaPipe's result (the page adds the brightness). See tracker.js.
function sample(r) {
  if (!r.faceLandmarks?.length) return { face: false };
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
  return {
    face: true, yaw, pitch,
    ix: (a[0] + (1 - b[0])) / 2, iy: (a[1] + b[1]) / 2,
    blink: Math.min(bs.eyeBlinkLeft || 0, bs.eyeBlinkRight || 0),
    // How centred the face is in the camera frame: 0 = centred, 1 = at the edge.
    offCentre: Math.max(Math.abs(nose.x - 0.5), Math.abs(nose.y - 0.5)) * 2,
    // Face width as a fraction of the frame: too small = too far away.
    size: Math.abs(L[454].x - L[234].x),
  };
}

self.onmessage = async ({ data }) => {
  if (data.type === 'load') {
    try { postMessage({ type: 'ready', ...await load(data.remembered) }); }
    catch (e) { postMessage({ type: 'error', message: String(e?.message || e) }); }
  } else if (data.type === 'frame') {
    let s = { face: false };
    // A frame that can't be read counts as no face (the page says so); the first error is logged.
    try {
      const t = performance.now();
      s = sample(landmarker.detectForVideo(data.frame, data.time)); failing = false;
      if (trial) {
        await judge(Math.round(performance.now() - t), data.frame, data.time)
          .catch((e) => { trial.cpu?.close(); decide('GPU', `the CPU didn’t work here (${e?.message || e})`); });
      }
    } catch (e) { if (!failing) console.error('Face tracking:', e); failing = true; }
    data.frame.close();
    postMessage({ type: 'sample', sample: s });
  }
};
