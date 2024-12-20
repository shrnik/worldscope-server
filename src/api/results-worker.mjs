import { Worker } from "bullmq";
import pgVector from "pgvector/knex";
import db from "./db.mjs";
import connection from "./redis-connection.mjs";
process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

console.log("Worker loaded");

async function processor(job) {
  try {
    const { url, cameraId, embedding, timestamp } = job.data;
    const embeddingArray = pgVector.toSql(embedding);
    console.time(job.id);
    console.log(job.id, "embedding created");

    await db.transaction(async (trx) => {
      const existingRecord = await trx("images")
        .select("updated_at")
        .where({ camera_id: cameraId })
        .first();

      if (
        !existingRecord ||
        new Date(timestamp) > new Date(existingRecord.updated_at)
      ) {
        await trx("images")
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
        console.log(job.id, "inserted into db");
      } else {
        console.log(job.id, "skipped insert due to timestamp");
      }
    });
  } catch (e) {
    console.error(e);
  } finally {
    console.timeEnd(job.id);
    return;
  }
}

const worker = new Worker("results", processor, {
  connection,
});

worker.on("completed", async (job) => {
  console.log("worker completed");
});

worker.on("error", (err) => {
  // log the error
  console.error(err);
});
