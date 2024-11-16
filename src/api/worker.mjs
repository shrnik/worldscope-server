import { Worker } from "bullmq";
import pgVector from "pgvector/knex";
import db from "./db.mjs";
import imageWorker from "./image-worker.mjs";
import timeout from "../utils/timeout.mjs";
import connection from "./redis-connection.mjs";
import { resultsQueue } from "./queue.mjs";

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

console.log("Worker loaded");

async function processor(job) {
  try {
    console.time(job.id);
    let result;
    try {
      result = await timeout(imageWorker(job), 5000);
    } catch {
      console.log("Error in imageWorker");
      return;
    }
    if (!result) {
      console.log("No result from imageWorker");
      return;
    }
    const { url, cameraId, embedding } = result;
    resultsQueue.add(
      "results",
      { url, cameraId, embedding, timestamp: new Date() },
      { removeOnComplete: true }
    );
  } catch (e) {
    console.error(e);
  } finally {
    console.timeEnd(job.id);
    return;
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
