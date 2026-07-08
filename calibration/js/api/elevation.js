/* Terrain elevation lookup (meters above sea level, ~90 m Copernicus DEM).
   Primary: open-meteo (no key, CORS, up to 100 coords per call);
   fallback: open-elevation. Results are cached per ~1 m grid cell. */

const cache = new Map();   // "lat,lon"@5dp -> meters
const key = (lat, lon) => `${lat.toFixed(5)},${lon.toFixed(5)}`;

async function openMeteoBatch(coords){
  const url = 'https://api.open-meteo.com/v1/elevation' +
    '?latitude=' + coords.map(c => c.lat.toFixed(6)).join(',') +
    '&longitude=' + coords.map(c => c.lon.toFixed(6)).join(',');
  const res = await fetch(url);
  if(!res.ok) throw new Error('open-meteo HTTP ' + res.status);
  const { elevation } = await res.json();
  if(!Array.isArray(elevation) || elevation.length !== coords.length)
    throw new Error('open-meteo returned an unexpected payload');
  return elevation;
}

async function openElevationBatch(coords){
  const res = await fetch('https://api.open-elevation.com/api/v1/lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locations: coords.map(c => ({ latitude: c.lat, longitude: c.lon })) }),
  });
  if(!res.ok) throw new Error('open-elevation HTTP ' + res.status);
  const { results } = await res.json();
  if(!Array.isArray(results) || results.length !== coords.length)
    throw new Error('open-elevation returned an unexpected payload');
  return results.map(r => r.elevation);
}

/* coords: [{lat, lon}] -> meters ASL, same order */
export async function fetchElevations(coords){
  const out = new Array(coords.length);
  const missing = [];
  coords.forEach((c, i) => {
    const hit = cache.get(key(c.lat, c.lon));
    if(hit !== undefined) out[i] = hit;
    else missing.push(i);
  });
  for(let at = 0; at < missing.length; at += 100){
    const idx = missing.slice(at, at + 100);
    const batch = idx.map(i => coords[i]);
    let elevs;
    try{ elevs = await openMeteoBatch(batch); }
    catch(e1){
      try{ elevs = await openElevationBatch(batch); }
      catch(e2){
        throw new Error(`elevation lookup failed (${e1.message}; fallback: ${e2.message}) — check the connection and retry`);
      }
    }
    idx.forEach((i, j) => {
      out[i] = elevs[j];
      cache.set(key(coords[i].lat, coords[i].lon), elevs[j]);
    });
    if(at + 100 < missing.length) await new Promise(ok => setTimeout(ok, 300));
  }
  return out;
}
