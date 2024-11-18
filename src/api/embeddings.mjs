import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  RawImage,
} from "@huggingface/transformers";

const quantized = false;

let imageProcessor = await AutoProcessor.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let visionModel = await CLIPVisionModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

async function makeImageEmbedding(imagePath) {
  const image = await RawImage.read(imagePath);
  const imageInputs = await imageProcessor(image);
  let { image_embeds } = await visionModel(imageInputs);
  return image_embeds.data;
}

export default makeImageEmbedding;
export { makeImageEmbedding };
