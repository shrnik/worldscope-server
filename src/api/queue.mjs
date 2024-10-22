import { Worker, Queue, RedisConnection } from "bullmq";

import db from "./db.mjs";
import utils from "./embeddings.mjs";
import pgVector from "pgvector/knex";
import { pathToFileURL, fileURLToPath } from "url";
import path, { dirname } from "path";

const connection = {
  host: "127.0.0.1",
  port: 6379,
};

const imageQueue = new Queue("images", { connection });

const __dirname = dirname(fileURLToPath(import.meta.url));

process.execArgv = process.execArgv.filter(
  (arg) => !arg.includes("--max-old-space-size=")
);
const workerPath = pathToFileURL(path.resolve(__dirname, "image-worker.mjs"));
const worker = new Worker("images", workerPath, {
  useWorkerThreads: true,
  concurrency: 2,
  connection,
});

worker.on("completed", async (job) => {
  console.log("queueProcessing completed");
  const { url, cameraId } = job.data;
  const { embedding } = job.returnvalue;
  const embeddingArray = pgVector.toSql(Array.from(embedding));

  try {
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
