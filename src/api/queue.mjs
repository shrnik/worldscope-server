import { Queue, Worker } from "bullmq";
import dotenv from "dotenv";
dotenv.config();
import { dirname } from "path";
import pgVector from "pgvector/knex";
import { fileURLToPath } from "url";
import db from "./db.mjs";
import imageWorker from "./image-worker.mjs";

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const connection = {
  host: process.env.REDIS_HOST,
  port: 6379,
  password: process.env.REDIS_PASSWORD,
};

const imageQueue = new Queue("images", { connection });

const __dirname = dirname(fileURLToPath(import.meta.url));

process.execArgv = process.execArgv.filter(
  (arg) => !arg.includes("--max-old-space-size=")
);

if (!process.env.WORKER_DISABLED) {
  console.log("worker started");
  const worker = new Worker("images", imageWorker, {
    connection,
  });

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
}
const convertToArray = (embedding) => {
  return Object.keys(embedding)
    .map(Number)
    .map((key) => embedding[key]);
};

console.log("imageQueue started");

export default imageQueue;
