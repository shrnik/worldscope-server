/* Vision LLM chat via HF Inference Providers router */
export async function vlmChat(content, { model, token, maxTokens = 1024, temperature = 0.2 }){
  if(!token) throw new Error('save an HF token in Settings first');
  const res = await fetch('https://router.huggingface.co/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
    body: JSON.stringify({
      model,
      messages: [{ role: 'user', content }],
      max_tokens: maxTokens,
      temperature,
    }),
  });
  if(!res.ok) throw new Error(`VLM HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return (await res.json()).choices[0].message.content;
}
