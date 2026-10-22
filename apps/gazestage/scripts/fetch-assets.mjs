// Copies the MediaPipe runtime into renderer/vendor and downloads the face model once,
// so the packaged app runs fully offline. Runs automatically after `npm install`.
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const vendor = join(root, 'renderer', 'vendor');
const mp = join(root, 'node_modules', '@mediapipe', 'tasks-vision');
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
const MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff';

mkdirSync(join(vendor, 'wasm'), { recursive: true });
cpSync(join(mp, 'vision_bundle.mjs'), join(vendor, 'vision_bundle.mjs'));
cpSync(join(mp, 'wasm'), join(vendor, 'wasm'), { recursive: true });

const model = join(vendor, 'face_landmarker.task');
const sha = (buf) => createHash('sha256').update(buf).digest('hex');
if (!existsSync(model) || sha(readFileSync(model)) !== MODEL_SHA256) {
  const res = await fetch(MODEL_URL);
  if (!res.ok) throw new Error(`Model download failed: HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  if (sha(buf) !== MODEL_SHA256) throw new Error('Model checksum mismatch');
  writeFileSync(model, buf);
}
console.log('GazeStage assets ready in renderer/vendor');
