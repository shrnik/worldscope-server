import {
  AutoTokenizer,
  CLIPTextModelWithProjection,
} from "@huggingface/transformers";

let tokenizer = await AutoTokenizer.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let textModel = await CLIPTextModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

async function makeTextEmbedding(text) {
  try {
    const textInputs = await tokenizer(text);
    let { text_embeds } = await textModel(textInputs);
    return text_embeds.data;
  } catch (e) {
    console.error(e);
  }
}

export default makeTextEmbedding;
