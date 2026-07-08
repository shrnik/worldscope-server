/* One-shot visual refinement: a mini agent with only the servoing tools,
   sharing the auto-calibrate runner plumbing. */
import { AGENT_TOOLS } from './tools.js';
import { REFINE_SYSTEM } from './system-prompt.js';
import { createAgentRunner } from './runner.js';

const REFINE_TOOL_NAMES = ['look_at_camera', 'adjust_params', 'revert_params'];

export function createRefineRunner(host, { maxTurns = 12, onFinish = null } = {}){
  return createAgentRunner(host, {
    tools: AGENT_TOOLS.filter(t => REFINE_TOOL_NAMES.includes(t.name)),
    systemPrompt: REFINE_SYSTEM,
    maxTurns,
    keepImages: 3,   // enough to compare before/after renders
    onFinish,
  });
}
