// A fake camera that shows a face, for the smoke test: MediaPipe's own test portrait, fetched
// (and checked) at test time rather than kept in the repository, made into a one-frame .y4m
// video that Chromium's fake camera plays on a loop (--use-file-for-fake-video-capture).
// The page decodes the photo, so no image tools are needed. Returns the file's path, or null
// when the photo can't be fetched (offline): the test then uses the plain fake camera.
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

const PORTRAIT = 'https://storage.googleapis.com/mediapipe-assets/portrait.jpg';
const PORTRAIT_SHA256 = 'a6f11efaa834706db23f275b6115058fa87fc7f14362681e6abe14e82749de3e';

export async function faceCamera(page, dir) {
  let photo;
  try {
    const res = await fetch(PORTRAIT, { signal: AbortSignal.timeout(15000) });
    photo = Buffer.from(await res.arrayBuffer());
    if (!res.ok || createHash('sha256').update(photo).digest('hex') !== PORTRAIT_SHA256) return null;
  } catch { return null; }
  // 640x480, from the top of the portrait where the face is, as YUV 4:2:0 (BT.601).
  const yuv = await page.evaluate(async (b64) => {
    const img = await createImageBitmap(new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))]));
    const W = 640, H = 480, ctx = new OffscreenCanvas(W, H).getContext('2d');
    ctx.drawImage(img, 0, 0, img.width, img.width * 3 / 4, 0, 0, W, H);
    const px = ctx.getImageData(0, 0, W, H).data, out = new Uint8Array(W * H * 3 / 2);
    for (let i = 0; i < W * H; i++) out[i] = 16 + ((66 * px[4 * i] + 129 * px[4 * i + 1] + 25 * px[4 * i + 2] + 128) >> 8);
    for (let y = 0; y < H / 2; y++) {
      for (let x = 0; x < W / 2; x++) {
        const p = 4 * (2 * y * W + 2 * x), r = px[p], g = px[p + 1], b = px[p + 2], i = y * W / 2 + x;
        out[W * H + i] = 128 + ((-38 * r - 74 * g + 112 * b + 128) >> 8);
        out[W * H * 5 / 4 + i] = 128 + ((112 * r - 94 * g - 18 * b + 128) >> 8);
      }
    }
    let s = '';
    for (let i = 0; i < out.length; i += 0x8000) s += String.fromCharCode(...out.subarray(i, i + 0x8000));
    return btoa(s);
  }, photo.toString('base64'));
  const file = join(dir, 'face.y4m');
  writeFileSync(file, Buffer.concat([Buffer.from('YUV4MPEG2 W640 H480 F30:1 Ip A1:1 C420jpeg\nFRAME\n'), Buffer.from(yuv, 'base64')]));
  return file;
}
