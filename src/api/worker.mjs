import { Worker } from "bullmq";
import dotenv from "dotenv";
import pgVector from "pgvector/knex";
import db from "./db.mjs";
import imageWorker from "./image-worker.mjs";
dotenv.config();

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const connection = {
  host: process.env.REDIS_HOST,
  port: 6379,
  password: process.env.REDIS_PASSWORD,
};

console.log("Worker loaded");

process.execArgv = process.execArgv.filter(
  (arg) => !arg.includes("--max-old-space-size=")
);

async function processor(job) {
  try {
    const result = await imageWorker(job);
    if (!result) {
      return;
    }
    const { url, cameraId, embedding } = result;
    const embeddingArray = pgVector.toSql(Array.from(embedding));
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
}

const worker = new Worker("images", processor, {
  connection,
});

worker.on("completed", async (job) => {
  console.log("worker completed");
});

worker.on("error", (err) => {
  // log the error
  console.error(err);
});