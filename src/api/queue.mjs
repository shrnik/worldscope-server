import Queue from "bull";

import db from "./db.mjs";
import utils from "./embeddings.mjs";
import pgVector from "pgvector/knex";

const { makeImageEmbedding } = utils;

const quantized = false;

const imageQueue = new Queue("images", "redis://127.0.0.1:6379");

imageQueue.process(2, async (job, done) => {
  console.log("queueProcessing started");
  const { url, cameraId } = job.data;
  try {
    const embedding = await makeImageEmbedding(url);
    const embeddingArray = pgVector.toSql(Array.from(embedding));
    await db("images")
      .insert({
        url,
        embedding: embeddingArray,
        camera_id: cameraId,
      })
      .onConflict("camera_id")
      .merge({
        embedding: embeddingArray,
      });
    done();
    console.log("queueProcessing ended,");
  } catch (e) {
    console.error(e);
  }
});

console.log("imageQueue started");

export default imageQueue;
