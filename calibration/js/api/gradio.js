/* Shared plain-fetch client for hosted Gradio Spaces. The @gradio/client
   library sends every request with credentials:'include', but the Spaces'
   preflight responses omit Access-Control-Allow-Credentials, so browsers
   block it. Credential-less fetch avoids the whole problem (the Spaces are
   public); the HF token is attached as a bearer when provided — needed for
   ZeroGPU quota / private Spaces, anonymous access keeps working without it. */

const authHeaders = token => token ? { Authorization: 'Bearer ' + token } : {};

/* extract the final payload from a gradio /call SSE result stream */
export function parseGradioSSE(text){
  let event = null;
  for(const line of text.split('\n')){
    if(line.startsWith('event:')) event = line.slice(6).trim();
    else if(line.startsWith('data:') && (event === 'complete' || event === 'error')){
      const payload = JSON.parse(line.slice(5));
      if(event === 'error') throw new Error(payload === null
        ? 'Space rejected the call with no detail — usually ZeroGPU denying quota; save a valid HF token in Settings.'
        : 'Space reported an error: ' + JSON.stringify(payload));
      return payload;
    }
  }
  throw new Error('Space stream ended without a result (it may be sleeping — retry in a minute).');
}

/* upload one blob; returns the server-side file path for gradio.FileData */
export async function gradioUpload(spaceUrl, blob, token, filename = 'frame.jpg'){
  const fd = new FormData();
  fd.append('files', blob, filename);
  const res = await fetch(`${spaceUrl}/gradio_api/upload`, {
    method: 'POST', headers: authHeaders(token), body: fd,
  });
  if(!res.ok) throw new Error(`upload failed (HTTP ${res.status})`);
  const [path] = await res.json();
  return path;
}

/* POST /gradio_api/call/<endpoint>, then read the event result stream */
export async function gradioCall(spaceUrl, endpoint, data, token){
  const auth = authHeaders(token);
  const callRes = await fetch(`${spaceUrl}/gradio_api/call/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth },
    body: JSON.stringify({ data }),
  });
  if(!callRes.ok) throw new Error(`call failed (HTTP ${callRes.status})`);
  const { event_id } = await callRes.json();
  const evRes = await fetch(`${spaceUrl}/gradio_api/call/${endpoint}/${event_id}`, { headers: auth });
  if(!evRes.ok) throw new Error(`result stream failed (HTTP ${evRes.status})`);
  return parseGradioSSE(await evRes.text());
}
