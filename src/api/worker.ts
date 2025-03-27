import { Job, Worker } from "bullmq";
import timeout from "../utils/timeout";
import imageWorker from "./image-worker";
import { resultsQueue } from "./queue";
import connection from "./redis-connection";

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

console.log("Worker loaded");

async function processor(job: Job) {
  console.time(job.id);
  const result = await timeout(imageWorker(job), 5000);
  if (!result) {
    console.log("No result from imageWorker");
    return;
  }
  const { url, cameraId, embedding } = result;
  resultsQueue.add(
    "results",
    {
      ...job.data,
      url,
      cameraId,
      embedding,
      timestamp: new Date(),
    },
    { removeOnComplete: true }
  );
  console.timeEnd(job.id);
  return;
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
