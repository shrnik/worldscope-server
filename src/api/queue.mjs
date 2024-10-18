import Queue from "bull";

import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  RawImage,
} from "@xenova/transformers";

import db from "./db.mjs";
import pgvector from "pgvector/knex";

const quantized = false;

let imageProcessor = await AutoProcessor.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let visionModel = await CLIPVisionModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

const imageQueue = new Queue("images", "redis://127.0.0.1:6379");

async function makeEmbedding(imagePath) {
  try {
    const image = await RawImage.read(imagePath);
    const imageInputs = await imageProcessor(image);
    let { image_embeds } = await visionModel(imageInputs);
    return image_embeds.data;
  } catch (e) {
    console.error(e);
  }
  console.timeEnd("image-embedding");
}

imageQueue.process(2, async (job) => {
  console.log("queueProcessing started");
  const { id, path } = job.data;
  try {
    const embeddings = await makeEmbedding(path);
    await db("images")
      .where({ id })
      .update({
        embeddings: pgvector.toSql(Array.from(embeddings)),
      });
    console.log("queueProcessing ended,", id);
  } catch (e) {
    console.error(e);
  }
});

console.log("imageQueue started");

export default imageQueue;
