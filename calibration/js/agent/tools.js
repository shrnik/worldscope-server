/* Agent tool schemas + executors. Executors reach the app only through the
   `host` object built in index.html — no direct DOM/state access here. */

export const AGENT_TOOLS = [
  { name: 'get_state',
    description: 'Current calibration state: image size, origin, camera GPS, parameters, all pairs with reprojection errors, overall RMS, and loaded OSM data counts.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'look_at_camera',
    description: 'Returns a render of the camera frame with every overlay drawn at the CURRENT parameters: projected OSM building outlines (teal), roads (orange), landmark dots, SAM3 masks/marks (magenta), and pairs (numbered crosses; the small dot of the same color is where that pair currently reprojects — cross far from dot = bad fit). Call this to identify landmarks in the scene and to visually verify calibration after solving.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'fetch_osm',
    description: 'Fetch OpenStreetMap context around the camera: building footprints, roads, and point landmarks (poles, signals, trees, signs...). Returns counts plus exact coordinates of landmarks and building corners for pairing.',
    input_schema: { type: 'object', properties: {
      radius_m: { type: 'number', description: 'Fetch radius in meters (50-600)', minimum: 50, maximum: 600 },
    }, required: ['radius_m'], additionalProperties: false } },
  { name: 'segment_object',
    description: 'SAM3 text-prompted segmentation on the camera frame. Give a short noun phrase ("red brick clock tower", "leftmost street lamp"); returns the exact full-resolution pixel centroid of the best match and draws its mask on the image. Small matches are automatically re-segmented on a native-resolution crop for precise pixels (zoomed: true in the result). For tiny or distant features SAM3 misses on the full frame, pass `region` — a full-res pixel rect around where you believe the feature is (from look_at_camera) — and only that crop is sent, at native resolution. Note: the centroid is the mask center of mass — for a building prefer pairing a corner or its base.',
    input_schema: { type: 'object', properties: {
      query: { type: 'string', description: '2-5 word noun phrase locating one object' },
      region: { type: 'object', description: 'Optional crop to segment within, in full-resolution frame pixels. Pad generously (2-3x the feature size).',
        properties: {
          x: { type: 'number' }, y: { type: 'number' },
          w: { type: 'number' }, h: { type: 'number' },
        }, required: ['x', 'y', 'w', 'h'], additionalProperties: false },
    }, required: ['query'], additionalProperties: false } },
  { name: 'wikipedia_lookup',
    description: 'Look up a named landmark on Wikipedia. Returns title, summary, URL, and — for geographic subjects — exact coordinates usable as the world side of a pair.',
    input_schema: { type: 'object', properties: {
      name: { type: 'string' },
    }, required: ['name'], additionalProperties: false } },
  { name: 'street_level_view',
    description: 'Nearest street-level photo (Mapillary) to a world coordinate, with its capture position and compass heading. Use it to see what a landmark looks like from the ground before pairing it, or to confirm a feature\'s identity. Fails gracefully when no photos exist nearby or no Mapillary token is saved.',
    input_schema: { type: 'object', properties: {
      lat: { type: 'number' }, lon: { type: 'number' },
    }, required: ['lat', 'lon'], additionalProperties: false } },
  { name: 'geocalib_seed',
    description: 'Run the GeoCalib neural network on the frame to estimate focal length, k1 distortion, pitch, and roll from image cues alone; applies them to the parameters. Good first step. Does NOT estimate yaw or position. May take a minute on a cold start.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'set_camera_position',
    description: 'Set the camera GPS position (and the local origin, if not set yet). Use once you have determined where the camera is — from operator notes, scene recognition, Wikipedia, or web search. Required before fetch_osm and add_pair can work when the user left position empty.',
    input_schema: { type: 'object', properties: {
      lat: { type: 'number' }, lon: { type: 'number' },
      height_m: { type: 'number', description: 'Camera height above local ground in meters, if known (e.g. rooftop mount)' },
    }, required: ['lat', 'lon'], additionalProperties: false } },
  { name: 'add_pair',
    description: 'Add an image<->world correspondence: pixel (u,v) in the full-resolution frame paired with a world coordinate (lat, lon, optional height above local ground in meters). When z_m is omitted the point is grounded on real terrain via a DEM lookup (the returned z_m is the applied value).',
    input_schema: { type: 'object', properties: {
      u: { type: 'number' }, v: { type: 'number' },
      lat: { type: 'number' }, lon: { type: 'number' },
      z_m: { type: 'number', description: 'Height above local ground of the world point (e.g. top of a 20 m tower = 20). Default 0 (ground).' },
      label: { type: 'string', description: 'Short name of the feature' },
    }, required: ['u', 'v', 'lat', 'lon'], additionalProperties: false } },
  { name: 'remove_pair',
    description: 'Delete a pair by its index (from get_state / solve_pose). Use on outliers.',
    input_schema: { type: 'object', properties: {
      index: { type: 'integer' },
    }, required: ['index'], additionalProperties: false } },
  { name: 'set_param',
    description: 'Directly set one camera parameter (e.g. a rough yaw guess before solving, or a known mounting height).',
    input_schema: { type: 'object', properties: {
      key: { type: 'string', enum: ['yaw', 'pitch', 'roll', 'f', 'height', 'k1', 'k2'] },
      value: { type: 'number' },
    }, required: ['key', 'value'], additionalProperties: false } },
  { name: 'adjust_params',
    description: 'Nudge pose parameters by small deltas and see the result: applies the deltas (clamped per call: |d_yaw|<=5, |d_pitch|<=3, |d_roll|<=2 degrees, |d_f_pct|<=10 percent, |d_height_m|<=3 m), then returns the fresh annotated render plus the new parameters and RMS. Reading the render: wireframe shifted LEFT of its image features => positive d_yaw (shifted right => negative); projected verticals leaning vs real ones => d_roll; ground geometry sitting too high/low => d_pitch and/or d_height_m; everything uniformly too large/small => d_f_pct. Make ONE small adjustment per call and compare renders. RMS may be n/a when no pairs exist — judge visually.',
    input_schema: { type: 'object', properties: {
      d_yaw: { type: 'number', description: 'Yaw delta in degrees (clamped to ±5)' },
      d_pitch: { type: 'number', description: 'Pitch delta in degrees (clamped to ±3)' },
      d_roll: { type: 'number', description: 'Roll delta in degrees (clamped to ±2)' },
      d_f_pct: { type: 'number', description: 'Focal length change in percent (clamped to ±10)' },
      d_height_m: { type: 'number', description: 'Camera height delta in meters (clamped to ±3)' },
    }, additionalProperties: false } },
  { name: 'revert_params',
    description: 'Restore the best-RMS parameter snapshot recorded during this refinement session (or the session-start parameters when no RMS is available). Use when adjustments made things worse.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'solve_pose',
    description: 'Solve the full camera pose from the current pairs (needs 4+; 6+ for distortion). Writes the solution to the parameters and returns RMS plus per-pair reprojection errors.',
    input_schema: { type: 'object', properties: {
      solve_focal: { type: 'boolean', description: 'Also optimize focal length (recommended unless geocalib_seed gave a confident f)' },
      solve_distortion: { type: 'boolean', description: 'Also optimize k1/k2 (needs 6+ pairs)' },
    }, additionalProperties: false } },
  { name: 'celestial_position',
    description: 'Azimuth/elevation of the sun or moon as seen from the camera at a given UTC time. Use to sanity-check before add_celestial_pair.',
    input_schema: { type: 'object', properties: {
      body: { type: 'string', enum: ['sun', 'moon'] },
      timestamp_utc: { type: 'string', description: 'ISO 8601 UTC time of the frame, e.g. 2026-07-03T18:40:00Z' },
    }, required: ['body', 'timestamp_utc'], additionalProperties: false } },
  { name: 'add_celestial_pair',
    description: 'If the sun or moon is visible in the frame AND the capture time is known (user notes, or a timestamp burned into the frame), pair its pixel position with its computed sky direction. One celestial pair strongly constrains yaw/pitch/roll — very valuable when few ground landmarks exist.',
    input_schema: { type: 'object', properties: {
      body: { type: 'string', enum: ['sun', 'moon'] },
      timestamp_utc: { type: 'string', description: 'ISO 8601 UTC capture time' },
      u: { type: 'number', description: 'Pixel x of the body center (full-res frame)' },
      v: { type: 'number', description: 'Pixel y of the body center' },
    }, required: ['body', 'timestamp_utc', 'u', 'v'], additionalProperties: false } },
];

/* annotated render + params/RMS text — shared by look_at_camera and the
   Phase-3 adjust_params feedback loop */
export function annotatedViewBlocks(host, note = ''){
  if(!host.hasImage()) throw new Error('no camera image loaded');
  const dataUrl = host.renderAnnotatedFrame();
  const rms = host.getRMS();
  const { w, h } = host.imageSize();
  return [
    { type: 'image', data: dataUrl.split(',')[1], mimeType: 'image/jpeg' },
    { type: 'text', text: `${note}Annotated render at current parameters. RMS: ${rms != null ? rms.toFixed(2) + ' px' : 'n/a (not solved yet)'}. Pixel coordinates you give in other tools must be in the full ${w}x${h} frame (this render is scaled by ${(Math.min(1, 1024/w)).toFixed(4)}).` },
  ];
}

export async function executeAgentTool(host, name, input){
  switch(name){
    case 'get_state':
      return host.getState();
    case 'look_at_camera':
      return annotatedViewBlocks(host);
    case 'fetch_osm': {
      const res = await host.fetchOSM(Math.min(600, Math.max(50, input.radius_m)));
      /* nearest landmarks first — the payload is capped and close features
         are the most likely to be identifiable in the frame */
      const st = host.getState();
      const cam = st.camera?.lat != null ? st.camera : st.origin;
      const d2 = l => cam ? (l.lat - cam.lat)**2 + ((l.lon - cam.lon) * Math.cos(cam.lat * Math.PI/180))**2 : 0;
      const landmarks = [...host.landmarks()].sort((a, b) => d2(a) - d2(b)).slice(0, 150)
        .map(l => ({ type: l.label, lat: +l.lat.toFixed(7), lon: +l.lon.toFixed(7),
                     ...(l.height ? { height_m: l.height } : {}) }));
      const buildings = host.footprints().slice(0, 40).map(fp => ({
        height_m: fp.height,
        corners: fp.ring.slice(0, 12).map(c => [+c[0].toFixed(7), +c[1].toFixed(7)]),
      }));
      return { counts: res, landmarks, buildings,
        note: 'corner/landmark coordinates are exact — prefer them as the world side of pairs. Landmarks with height_m are tall vertical structures: pair their base at z=0 or their top at z=height_m.' };
    }
    case 'segment_object': {
      let region = null;
      if(input.region){
        const { w: imgW, h: imgH } = host.imageSize();
        const cl = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
        const x = cl(input.region.x, 0, imgW - 1), y = cl(input.region.y, 0, imgH - 1);
        region = { x, y, w: cl(input.region.w, 16, imgW - x), h: cl(input.region.h, 16, imgH - y) };
      }
      return await host.sam3Segment(input.query, region);
    }
    case 'wikipedia_lookup':
      return await host.wikiLookup(input.name);
    case 'street_level_view':
      return await host.streetLevelView(input.lat, input.lon);
    case 'geocalib_seed':
      return await host.geoCalibSeed();
    case 'set_camera_position':
      return host.setCameraPosition(input.lat, input.lon, input.height_m);
    case 'add_pair':
      return await host.addPair(input);
    case 'remove_pair':
      return host.removePair(input.index);
    case 'set_param':
      host.setParam(input.key, input.value);
      return { [input.key]: input.value };
    case 'adjust_params': {
      const r = host.adjustParams(input ?? {});
      const blocks = annotatedViewBlocks(host, r.note);
      blocks.push({ type: 'text', text:
        'Params now: ' + JSON.stringify(host.getState().params) +
        ' · best RMS this session: ' + (r.best_rms != null ? r.best_rms.toFixed(2) + ' px' : 'n/a') });
      return blocks;
    }
    case 'revert_params':
      return host.revertParams();
    case 'solve_pose':
      return host.solvePose({ solveFocal: !!input.solve_focal, solveDistortion: !!input.solve_distortion });
    case 'celestial_position':
      return host.celestialPosition(input.body, input.timestamp_utc);
    case 'add_celestial_pair':
      return host.addCelestialPair(input.body, input.timestamp_utc, input.u, input.v);
    default:
      throw new Error('unknown tool: ' + name);
  }
}

/* one-line result digest for the live log */
export function agentToolSummary(name, out){
  try{
    switch(name){
      case 'solve_pose':          return `RMS ${out.rms.toFixed(2)} px`;
      case 'fetch_osm':           return `${out.counts.buildings} bld · ${out.counts.roads} rd · ${out.counts.landmarks} lm`;
      case 'segment_object':      return `px (${out.u}, ${out.v})${out.zoomed ? ' · auto-zoomed' : ''}`;
      case 'geocalib_seed':       return out.applied.join(' · ');
      case 'add_pair':            return `#${out.pair_index + 1} (${out.pair_count} total)`;
      case 'wikipedia_lookup':    return out.coordinates ? `@ ${out.coordinates.lat.toFixed(5)}, ${out.coordinates.lon.toFixed(5)}` : 'no coordinates';
      case 'set_camera_position': return `${out.camera.lat.toFixed(5)}, ${out.camera.lon.toFixed(5)}`;
      case 'revert_params':       return `${out.restored}${out.rms != null ? ` · RMS ${out.rms.toFixed(2)} px` : ''}`;
      case 'celestial_position':  return `az ${out.azimuth_deg}° el ${out.elevation_deg}°`;
      case 'add_celestial_pair':  return `az ${out.azimuth_deg}° el ${out.elevation_deg}° → #${out.pair_index + 1}`;
    }
  }catch(_){ /* summaries are cosmetic */ }
  return '';
}
