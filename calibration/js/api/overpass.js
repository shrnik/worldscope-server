/* Overpass API client: building footprints, roads, and landmark nodes.
   Landmark classes mirror fetch_context.py's DEFAULT_OSM_FILTERS. */

const D2R = Math.PI / 180;

export const OSM_LANDMARK_FILTERS = [
  'node["highway"="street_lamp"]',
  'node["man_made"="manhole"]',
  'node["man_made"="utility_pole"]',
  'node["power"="pole"]',
  'node["highway"="traffic_signals"]',
  'node["highway"="stop"]',
  'node["traffic_sign"]',
  'node["amenity"="bench"]',
  'node["natural"="tree"]',
];

/* [south, west, north, east] covering ±radius meters around a point */
export function bboxAround(lat, lon, radiusM){
  const dLat = radiusM / 111320, dLon = radiusM / (111320 * Math.cos(lat * D2R));
  return [lat - dLat, lon - dLon, lat + dLat, lon + dLon];
}

export function buildCalibrationQuery(lat, lon, radiusM, filters = OSM_LANDMARK_FILTERS){
  const bbox = bboxAround(lat, lon, radiusM).map(v => v.toFixed(7)).join(',');
  return `
    [bbox:${bbox}]
    [out:json]
    [timeout:90]
    ;
    (
      way["building"];
      way["highway"];
      ${filters.map(f => f + ';').join('\n      ')}
    );
    out body geom;
  `;
}

/* Content-Type must be form-urlencoded — a bare string body is sent as
   text/plain and overpass-api.de answers 406. Mirrors tried in order. */
const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
];

export async function overpassFetch(query){
  let lastErr = null;
  for(const ep of ENDPOINTS){
    try{
      return await fetch(ep, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'data=' + encodeURIComponent(query),
      }).then(resp => {
        if(!resp.ok) throw new Error('HTTP ' + resp.status + ' from ' + new URL(ep).host);
        return resp.json();
      });
    }catch(err){ lastErr = err; }
  }
  throw lastErr || new Error('all Overpass endpoints failed');
}

export function buildingHeight(tags){
  if(!tags) return 6;
  const h = parseFloat(tags.height); if(!isNaN(h)) return h;
  const l = parseFloat(tags['building:levels']); if(!isNaN(l)) return l*3;
  return 6;
}

export function landmarkLabel(tags){
  return tags.man_made || tags.highway || tags.power || tags.natural ||
         tags.amenity || (tags.traffic_sign ? 'traffic_sign' : 'node');
}
