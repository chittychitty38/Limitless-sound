// Face tracking in its own thread. Loading MediaPipe and reading each frame can take seconds
// on a computer without a fast graphics chip; here it never freezes the window or holds up
// answers to other Limitless Sound apps. A classic worker (not a module one), because MediaPipe
// loads its WebAssembly with importScripts.
//   in:  { type: 'load' }, then { type: 'frame', frame: ImageBitmap, time }
//   out: { type: 'ready' } or { type: 'error', message }, then { type: 'sample', sample } per frame
'use strict';
const VENDOR = new URL('vendor/', self.location.href).href;
let landmarker = null, failing = false;

async function load() {
  const vision = await import(VENDOR + 'vision_bundle.mjs');
  const files = await vision.FilesetResolver.forVisionTasks(VENDOR + 'wasm');
  const opts = (delegate) => ({
    baseOptions: { modelAssetPath: VENDOR + 'face_landmarker.task', delegate },
    runningMode: 'VIDEO', numFaces: 1,
    outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
  });
  try { landmarker = await vision.FaceLandmarker.createFromOptions(files, opts('GPU')); }
  catch { landmarker = await vision.FaceLandmarker.createFromOptions(files, opts('CPU')); }
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
    try { if (!landmarker) await load(); postMessage({ type: 'ready' }); }
    catch (e) { postMessage({ type: 'error', message: String(e?.message || e) }); }
  } else if (data.type === 'frame') {
    let s = { face: false };
    // A frame that can't be read counts as no face (the page says so); the first error is logged.
    try { s = sample(landmarker.detectForVideo(data.frame, data.time)); failing = false; }
    catch (e) { if (!failing) console.error('Face tracking:', e); failing = true; }
    data.frame.close();
    postMessage({ type: 'sample', sample: s });
  }
};
