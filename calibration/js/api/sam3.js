/* SAM3 Space client: text-prompted segmentation of a frame crop. */
import { gradioUpload, gradioCall } from './gradio.js';

export const SAM3_URL = 'https://shrnik-sam3-demo.hf.space';

/* load a SAM3 mask image: centroid of its non-empty pixels + a magenta-tinted
   translucent overlay canvas for drawing on the camera image */
export function loadMask(url){
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = () => {
      const w = im.naturalWidth, h = im.naturalHeight;
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      const g = c.getContext('2d');
      g.drawImage(im, 0, 0);
      const src = g.getImageData(0, 0, w, h);
      const d = src.data;
      const tint = g.createImageData(w, h);
      const t = tint.data;
      let sx = 0, sy = 0, n = 0;
      let bx0 = w, by0 = h, bx1 = 0, by1 = 0;
      for(let y = 0; y < h; y++) for(let x = 0; x < w; x++){
        const i = (y*w + x) * 4;
        if(d[i+3] > 127 && (d[i] + d[i+1] + d[i+2]) > 30){
          sx += x; sy += y; n++;
          if(x < bx0) bx0 = x; if(x > bx1) bx1 = x;
          if(y < by0) by0 = y; if(y > by1) by1 = y;
          t[i] = 214; t[i+1] = 51; t[i+2] = 108; t[i+3] = 110;   // translucent #d6336c
        }
      }
      if(!n) return reject(new Error('empty mask'));
      g.putImageData(tint, 0, 0);
      resolve({ cx: sx/n, cy: sy/n, bx0, by0, bx1, by1, canvas: c });
    };
    im.onerror = () => reject(new Error('mask image load failed'));
    im.src = url;
  });
}

/* one SAM3 Space call on a prepared frame crop ({blob, ox, oy, rw, rh});
   returns the mask + the full-res rect it covers.
   The Space runs on ZeroGPU: anonymous API calls are rejected by the GPU
   scheduler (SSE answers "event: error, data: null") — pass the HF token
   so the call gets quota. */
export async function sam3Call(frame, query, token){
  const { blob, ox, oy, rw, rh } = frame;
  const path = await gradioUpload(SAM3_URL, blob, token);
  const runOnce = () => gradioCall(SAM3_URL, 'run_image_segmentation',
    [ { path, meta: { _type: 'gradio.FileData' } }, query, 0.45 ], token);
  let payload;
  try{ payload = await runOnce(); }
  catch(err){
    /* the SSE stream sometimes ends empty (Space waking up / idle connection
       cut); the event result is gone once read, so re-run the call once */
    if(!/stream ended without a result/.test(err.message)) throw err;
    payload = await runOnce();
  }
  /* AnnotatedImage payload: {image, annotations:[{image:FileData, label}]}; tolerate tuples */
  const ann = payload?.[0]?.annotations || [];
  if(!ann.length) throw new Error(`SAM3 found no match for "${query}"`);
  const maskUrl = ann[0]?.image?.url || ann[0]?.[0]?.url || ann[0]?.url;
  if(!maskUrl) throw new Error('unexpected mask payload shape');
  const mask = await loadMask(maskUrl);
  return { mask, rect: { x: ox, y: oy, w: rw, h: rh }, instances: ann.length };
}
