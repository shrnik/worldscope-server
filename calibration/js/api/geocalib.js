/* GeoCalib Space client: single-image neural estimate of focal length,
   k1 distortion, pitch, and roll. Yaw/position can't come from one image. */
import { gradioUpload, gradioCall } from './gradio.js';

export const GEOCALIB_URL = 'https://shrnik-geocalib.hf.space';

const D2R = Math.PI / 180;

export async function geoCalibPredict(blob, token){
  const path = await gradioUpload(GEOCALIB_URL, blob, token);
  return gradioCall(GEOCALIB_URL, 'process_results', [
    { path, meta: { _type: 'gradio.FileData' } },
    'simple_radial',
    false, false, false, false, false,
  ], token);
}

/* pull numbers out of the Space's free-text result; sentH is the height of
   the uploaded (possibly downscaled) image, for the vfov -> focal fallback */
export function parseGeoCalibText(raw, sentH){
  const num = label => {
    const m = raw.match(new RegExp(label + '[^\\-\\d]{0,12}(-?\\d+(?:\\.\\d+)?)', 'i'));
    return m ? parseFloat(m[1]) : null;
  };
  const out = { roll: num('roll'), pitch: num('pitch'), k1: num('k1') };
  let f = num('focal');
  if(f === null){
    const vfov = num('vfov') ?? num('v[ _-]?fov') ?? num('\\bfov');
    if(vfov !== null) f = (sentH/2) / Math.tan(vfov*D2R/2);
  }
  out.f = f;
  return out;
}
