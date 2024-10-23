import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  RawImage,
  AutoTokenizer,
  CLIPTextModelWithProjection,
} from "@xenova/transformers";

const quantized = false;

let imageProcessor = await AutoProcessor.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let visionModel = await CLIPVisionModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

let tokenizer = await AutoTokenizer.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let textModel = await CLIPTextModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

async function makeImageEmbedding(imagePath) {
  try {
    const image = await RawImage.read(imagePath);
    const imageInputs = await imageProcessor(image);
    let { image_embeds } = await visionModel(imageInputs);
    return image_embeds.data;
  } catch (e) {
    console.error(e);
  }
}

async function makeTextEmbedding(text) {
  try {
    const textInputs = await tokenizer(text);
    let { text_embeds } = await textModel(textInputs);
    return text_embeds.data;
  } catch (e) {
    console.error(e);
  }
}

export default {
  makeImageEmbedding,
  makeTextEmbedding,
};
