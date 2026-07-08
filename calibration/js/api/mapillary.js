/* Mapillary Graph API client: street-level photos near a point, for
   cross-referencing landmarks from the ground. Needs a (free) client
   token — created at mapillary.com/dashboard/developers. */
import { bboxAround } from './overpass.js';

export async function fetchMapillaryImages({ lat, lon, radiusM = 150, token, limit = 20 }){
  if(!token) throw new Error('save a Mapillary client token in Settings first');
  const [s, w, n, e] = bboxAround(lat, lon, radiusM);
  const url = 'https://graph.mapillary.com/images' +
    '?access_token=' + encodeURIComponent(token) +
    '&fields=id,computed_geometry,compass_angle,captured_at,thumb_1024_url,is_pano' +
    `&bbox=${w.toFixed(7)},${s.toFixed(7)},${e.toFixed(7)},${n.toFixed(7)}` +
    '&limit=' + limit;
  const res = await fetch(url);
  if(!res.ok) throw new Error(`Mapillary HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const { data } = await res.json();
  return (data || []).map(d => ({
    id: d.id,
    lat: d.computed_geometry?.coordinates?.[1],
    lon: d.computed_geometry?.coordinates?.[0],
    compass_angle: d.compass_angle ?? null,
    captured_at: d.captured_at ? new Date(d.captured_at).toISOString() : null,
    thumb_url: d.thumb_1024_url || null,
    is_pano: !!d.is_pano,
  })).filter(d => d.lat != null);
}
