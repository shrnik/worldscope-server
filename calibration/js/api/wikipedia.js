/* landmark name -> Wikipedia search + summary (+ coordinates when the
   subject is geographic) */
export async function wikiLookup(name){
  const s = await fetch('https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&origin=*&srlimit=1&srsearch=' +
    encodeURIComponent(name)).then(r => r.json());
  const hit = s.query?.search?.[0];
  if(!hit) throw new Error('no Wikipedia match for "' + name + '"');
  const sum = await fetch('https://en.wikipedia.org/api/rest_v1/page/summary/' +
    encodeURIComponent(hit.title)).then(r => r.json());
  return {
    title: sum.title,
    extract: sum.extract || '',
    url: sum.content_urls?.desktop?.page || null,
    coordinates: sum.coordinates ? { lat: sum.coordinates.lat, lon: sum.coordinates.lon } : null,
  };
}
