import { Job } from "bullmq";
import { makeImageEmbedding } from "./embeddings";

type ImageResult = {
  url: string;
  cameraId: string;
  embedding: number[];
};
export default async function (job: Job): Promise<ImageResult> {
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
