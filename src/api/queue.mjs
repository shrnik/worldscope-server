import { Worker, Queue, RedisConnection, Job } from "bullmq";

import db from "./db.mjs";
import utils from "./embeddings.mjs";
import pgVector from "pgvector/knex";
import { pathToFileURL, fileURLToPath } from "url";
import path, { dirname } from "path";
import imageWorker from "./image-worker.mjs";

const connection = {
  host: "127.0.0.1",
  port: 6379,
};

const imageQueue = new Queue("images", { connection });

const __dirname = dirname(fileURLToPath(import.meta.url));

process.execArgv = process.execArgv.filter(
  (arg) => !arg.includes("--max-old-space-size=")
);

const worker = new Worker("images", imageWorker, {
  connection,
});

const convertToArray = (embedding) => {
  return Object.keys(embedding)
    .map(Number)
    .map((key) => embedding[key]);
};

worker.on("completed", async (job) => {
  console.log("queueProcessing completed");

  try {
    const { url, cameraId } = job.data;
    const { embedding } = job.returnvalue;
    const embeddingArray = pgVector.toSql(convertToArray(embedding));
    await db("images")
      .insert({
        url,
        embedding: embeddingArray,
        camera_id: cameraId,
        created_at: db.fn.now(),
        updated_at: db.fn.now(),
      })
      .onConflict("camera_id")
      .merge({
        embedding: embeddingArray,
        updated_at: db.fn.now(),
      });
  } catch (e) {
    console.error(e);
  }
});

console.log("imageQueue started");

export default imageQueue;
