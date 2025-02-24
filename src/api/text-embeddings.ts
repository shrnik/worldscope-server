import {
  AutoTokenizer,
  CLIPTextModelWithProjection,
  SiglipTextModel,
  PreTrainedModel,
  PreTrainedTokenizer,
} from "@huggingface/transformers";

let tokenizer: PreTrainedTokenizer;
let textModel: PreTrainedModel;

let isLoaded = false;
let isLoading = false;
let loadPromise: Promise<void> | null = null;

const MODEL = "Xenova/siglip-base-patch16-224";
async function initialize() {
  if (isLoaded) return;
  if (isLoading) return loadPromise;

  isLoading = true;
  loadPromise = (async () => {
    try {
      tokenizer = await AutoTokenizer.from_pretrained(MODEL);
      textModel = await SiglipTextModel.from_pretrained(MODEL);
      isLoaded = true;
    } finally {
      isLoading = false;
    }
  })();

  return loadPromise;
}

initialize();

async function makeTextEmbedding(text: string) {
  await initialize();
  try {
    const textInputs = await tokenizer(text);
    let { pooler_output } = await textModel(textInputs);
    return Array.from(pooler_output.data) as number[];
  } catch (e) {
    console.error(e);
  }
}

export default makeTextEmbedding;
