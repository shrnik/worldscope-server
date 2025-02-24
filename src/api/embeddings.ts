import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  SiglipVisionModel,
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

const MODEL = "Xenova/siglip-base-patch16-224";

async function initialize() {
  if (isLoaded) return;
  if (isLoading) return loadPromise;

  isLoading = true;
  loadPromise = (async () => {
    try {
      imageProcessor = await AutoProcessor.from_pretrained(MODEL, {});
      visionModel = await SiglipVisionModel.from_pretrained(MODEL);
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
  let { pooler_output } = await visionModel(imageInputs);
  return Array.from(pooler_output.data);
}

export default makeImageEmbedding;
export { makeImageEmbedding };
