import { Job } from "bullmq";
import utils from "./embeddings.mjs";

const { makeImageEmbedding } = utils;

export default async function (job) {
  console.log("queueProcessing started");
  const { url, cameraId } = job.data;
  try {
    if (!url) {
      throw new Error("url is required");
    }
    const embedding = await makeImageEmbedding(url);
    if (!embedding) {
      throw new Error("Failed to get embedding");
    }

    return { url, cameraId, embedding };
  } catch (e) {
    console.error(e);
    done(e);
  }
}
