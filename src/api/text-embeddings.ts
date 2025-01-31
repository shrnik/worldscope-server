import {
  AutoTokenizer,
  CLIPTextModelWithProjection,
  PreTrainedModel,
  PreTrainedTokenizer,
} from "@huggingface/transformers";

let tokenizer: PreTrainedTokenizer;
let textModel: PreTrainedModel;

let isLoaded = false;
let isLoading = false;
let loadPromise: Promise<void> | null = null;

async function initialize() {
  if (isLoaded) return;
  if (isLoading) return loadPromise;

  isLoading = true;
  loadPromise = (async () => {
    try {
      tokenizer = await AutoTokenizer.from_pretrained(
        "Xenova/clip-vit-base-patch16"
      );
      textModel = await CLIPTextModelWithProjection.from_pretrained(
        "Xenova/clip-vit-base-patch16"
      );
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
    let { text_embeds } = await textModel(textInputs);
    return Array.from(text_embeds.data) as number[];
  } catch (e) {
    console.error(e);
  }
}

export default makeTextEmbedding;
