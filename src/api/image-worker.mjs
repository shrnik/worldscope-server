import { Job } from "bullmq";
import { makeImageEmbedding } from "./embeddings.mjs";
import pgVector from "pgvector/knex";

export default async function (job) {
  const { url, cameraId } = job.data;
  if (!url) {
    throw new Error("url is required");
  }
  const embedding = await makeImageEmbedding(url);
  if (!embedding) {
    throw new Error("Failed to get embedding");
  }
  return { url, cameraId, embedding: Array.from(embedding) };
}
