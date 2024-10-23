import { Job } from "bullmq";
import utils from "./embeddings.mjs";

const { makeImageEmbedding } = utils;

export default async function (job) {
  console.time(job.id);
  const { url, cameraId } = job.data;
  try {
    if (!url) {
      throw new Error("url is required");
    }
    const embedding = await makeImageEmbedding(url);
    if (!embedding) {
      throw new Error("Failed to get embedding");
    }
    console.timeEnd(job.id);

    return { url, cameraId, embedding };
  } catch (e) {
    console.error(e);
  }
  console.timeEnd(job.id);
}
