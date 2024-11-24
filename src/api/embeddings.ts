import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  PreTrainedModel,
  Processor,
  RawImage,
} from "@huggingface/transformers";

const quantized = false;

let imageProcessor: Processor;
let visionModel: PreTrainedModel;

let isLoaded = false;
let isLoading = false;
let loadPromise: Promise<void> | null = null;

async function initialize() {
  if (isLoaded) return;
  if (isLoading) return loadPromise;

  isLoading = true;
  loadPromise = (async () => {
    try {
      imageProcessor = await AutoProcessor.from_pretrained(
        "Xenova/clip-vit-base-patch16"
      );
      visionModel = await CLIPVisionModelWithProjection.from_pretrained(
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

async function makeImageEmbedding(imagePath: string) {
  await initialize();
  const image = await RawImage.read(imagePath);
  const imageInputs = await imageProcessor(image);
  let { image_embeds } = await visionModel(imageInputs);
  return image_embeds.data;
}

export default makeImageEmbedding;
export { makeImageEmbedding };
