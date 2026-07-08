/* pi-agent-core plumbing shared by the auto-calibrate agent and the
   visual-refine mini agent. The app is reached only through `host`. */
import { AGENT_TOOLS, executeAgentTool, agentToolSummary } from './tools.js';
import { AGENT_SYSTEM } from './system-prompt.js';

let piAgentModule = null;   // lazy-loaded on the first run
export function loadPiAgent(){
  return piAgentModule ??= import('https://esm.sh/@earendil-works/pi-agent-core@0.80.3?bundle')
    .catch(err => {
      piAgentModule = null;
      throw new Error('could not load the agent runtime from esm.sh (offline or CDN down?): ' + (err?.message || err));
    });
}

/* pi-ai Model record for an arbitrary HF router model id */
export function agentModelFor(id){
  return {
    id, name: id,
    api: 'openai-completions',
    provider: 'huggingface',
    baseUrl: 'https://router.huggingface.co/v1',
    reasoning: false,
    input: ['text', 'image'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128000,
    maxTokens: 8192,
  };
}

/* keep only the newest images in the transcript (the frame is re-obtainable
   via look_at_camera); older ones become placeholders so tokens stay bounded.
   Used as the agent's transformContext — copy-on-write, the stored transcript
   keeps its images */
export function pruneAgentImages(messages, keep = 2){
  let total = 0;
  for(const m of messages) if(Array.isArray(m.content))
    for(const b of m.content) if(b.type === 'image') total++;
  let toDrop = Math.max(0, total - keep);
  if(!toDrop) return messages;
  return messages.map(m => {
    if(!Array.isArray(m.content) || !m.content.some(b => b.type === 'image')) return m;
    const content = m.content.map(b => {
      if(b.type === 'image' && toDrop > 0){
        toDrop--;
        return { type: 'text', text: '[earlier frame render pruned — call look_at_camera for a fresh one]' };
      }
      return b;
    });
    return { ...m, content };
  });
}

/* tools as pi AgentTool records: executeAgentTool does the work, the wrapper
   adapts results (pi tool results carry text and image blocks) and feeds the
   live log */
function wrapToolsForPi(host, tools){
  return tools.map(t => ({
    name: t.name,
    label: t.name,
    description: t.description,
    parameters: t.input_schema,
    execute: async (toolCallId, params) => {
      const argStr = JSON.stringify(params ?? {});
      try{
        const out = await executeAgentTool(host, t.name, params ?? {});
        const digest = agentToolSummary(t.name, out);
        host.agentLog('al-tool', `→ ${t.name} ${argStr.length > 90 ? argStr.slice(0, 90) + '…' : argStr} ✓${digest ? ' — ' + digest : ''}`);
        return { content: Array.isArray(out) ? out
          : [{ type: 'text', text: typeof out === 'string' ? out : JSON.stringify(out) }] };
      }catch(err){
        /* never throw: a failed tool becomes a normal text result, so the run
           keeps going and the model can retry or route around it */
        const reason = err?.message || String(err);
        host.agentLog('al-tool err', `→ ${t.name} ✗ ${reason}`);
        return { content: [{ type: 'text', text:
          `${t.name} failed: ${reason}. This is not fatal — adjust the arguments (different query, region, or values) or continue with another approach.` }] };
      }
    },
  }));
}

export function createAgentRunner(host, {
  tools = AGENT_TOOLS,
  systemPrompt = AGENT_SYSTEM,
  maxTurns = 40,
  keepImages = 2,
  onFinish = null,
} = {}){
  let agent = null;         // survives interrupts so continue() can resume
  let turns = 0;
  let goalSent = '';
  let stopped = false;

  /* shared runner around prompt()/continue(): busy state, interrupt wiring,
     auto-resume on transient API errors, final status */
  async function drive(run){
    stopped = false;
    setButtons(true);
    try{
      await run();
      /* transient API failure (rate limit, provider blip): resume the run from
         the surviving context instead of ending it. continue() needs the last
         message to be user/toolResult — drop the errored assistant tail first. */
      for(let retry = 0; agent?.state.errorMessage && !stopped && retry < 3; retry++){
        const msgs = agent.state.messages;
        while(msgs.length && msgs.at(-1).role === 'assistant') msgs.pop();
        if(!msgs.length || turns >= maxTurns) break;
        const waitMs = 2000 * Math.pow(2, retry);
        host.agentLog('al-tool', `… API error (${agent.state.errorMessage.slice(0, 120)}), resuming in ${Math.round(waitMs/1000)} s`);
        await new Promise(ok => setTimeout(ok, waitMs));
        if(stopped) break;
        await agent.continue();
      }
      if(stopped){
        host.agentLog('al-tool err', '⏸ interrupted — Continue resumes from here (edit the notes box to steer)');
        host.setMsg('Agent interrupted — press Continue to resume.');
      } else if(agent?.state.errorMessage){
        host.agentLog('al-tool err', 'Agent error: ' + agent.state.errorMessage);
        host.setMsg('Agent error: ' + agent.state.errorMessage);
      } else {
        const rms = host.getRMS();
        host.setMsg('Agent finished' + (rms != null ? ` — RMS ${rms.toFixed(2)} px.` : '.'));
      }
    }catch(err){
      host.agentLog('al-tool err', 'Agent error: ' + err.message);
      host.setMsg('Agent error: ' + err.message);
    }finally{
      setButtons(false);
      if(onFinish) try{ onFinish({ stopped }); }catch(_){ /* cosmetic */ }
    }
  }

  function setButtons(running){
    host.agentButtons?.(running, !!agent?.state.messages.length);
  }

  async function buildAgent(){
    const { Agent } = await loadPiAgent();
    agent = new Agent({
      initialState: {
        systemPrompt,
        model: agentModelFor(host.agentModelId()),
        tools: wrapToolsForPi(host, tools),
      },
      getApiKey: async () => host.hfToken(),
      transformContext: messages => pruneAgentImages(messages, keepImages),
      toolExecution: 'sequential',
    });
    agent.subscribe(event => {
      if(event.type === 'message_end' && event.message.role === 'assistant'){
        const text = (event.message.content || [])
          .filter(b => b.type === 'text').map(b => b.text).join('\n').trim();
        if(text) host.agentLog(event.message.stopReason === 'stop' ? 'al-text al-final' : 'al-text', text);
      }
      if(event.type === 'turn_end' && ++turns >= maxTurns - 3){
        if(turns >= maxTurns) agent.abort();
        else agent.steer({ role: 'user', timestamp: Date.now(), content:
          `[system] Only ${maxTurns - turns} step(s) left before the run is cut off — solve with the pairs you have, verify once with look_at_camera, and give your final summary now.` });
      }
    });
    return agent;
  }

  return {
    hasContext: () => !!agent?.state.messages.length,
    abort(){ stopped = true; agent?.abort(); },

    /* fresh run: prompt text + optional image blocks alongside it */
    run(goal, promptText, blocks = []){
      agent = null;
      turns = 0;
      goalSent = goal || '';
      return drive(async () => {
        await buildAgent();
        await agent.prompt(promptText, blocks);
      });
    },

    /* resume an interrupted/errored run; a changed note becomes a new prompt */
    continueRun(note){
      if(!agent || !agent.state.messages.length)
        return Promise.reject(new Error('nothing to continue — run the agent first'));
      return drive(async () => {
        /* an interrupted/errored run may end on an assistant message;
           continue() needs user/toolResult last, so drop the dangling tail */
        const msgs = agent.state.messages;
        while(msgs.length && msgs.at(-1).role === 'assistant') msgs.pop();
        if(!msgs.length) throw new Error('no context left to continue from — start a new run');
        /* grant more turn budget so a resumed run isn't cut off immediately */
        turns = Math.min(turns, maxTurns - 10);
        if(note && note !== goalSent){
          goalSent = note;
          await agent.prompt('Operator note: ' + note + '\n\nContinue calibrating with this in mind.');
        } else {
          await agent.continue();
        }
      });
    },
  };
}
