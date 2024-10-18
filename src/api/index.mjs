import express from "express";

import pgvector from "pgvector/knex";

import {
  AutoProcessor,
  CLIPVisionModelWithProjection,
  RawImage,
  AutoTokenizer,
  CLIPTextModelWithProjection,
} from "@xenova/transformers";

import db from "./db.mjs";
import imageQueue from "./queue.mjs";
import downloadAll from "./downloader.mjs";
import Bluebird from "bluebird";

const quantized = false;

let tokenizer = await AutoTokenizer.from_pretrained(
  "Xenova/clip-vit-base-patch16"
);
let textModel = await CLIPTextModelWithProjection.from_pretrained(
  "Xenova/clip-vit-base-patch16",
  { quantized }
);

const router = express.Router();

// create a table in the database to store the image features using Knex
db.schema
  .raw("CREATE EXTENSION IF NOT EXISTS vector")
  .createTableIfNotExists("images", (table) => {
    table.increments("id");
    table.string("path");
    table.string("cameraId");
    table.bigInteger("timeStamp");
    table.vector("embeddings", 512);
  })
  .then(() => {
    console.log("table created");
  })
  .catch((err) => {
    console.error(err);
  });
// await db.schema.alterTable("images", function (table) {
//   table.index(db.raw("embeddings vector_l2_ops"), "images_hnsw_index", "hnsw");
// });
// download all images from a set of URLs
// and store the images with their embeddings and metadata in the database

router.post("/images", async (req, res) => {
  const data = await downloadAll("./public");
  console.log(data.length);
  await Bluebird.map(
    data,
    async ({ cameraId, timeStamp, path }) => {
      try {
        const [{ id }] = await db("images").insert(
          {
            path,
            cameraId,
            timeStamp,
          },
          ["id", "path"]
        );
        // publish a message to the queue
        console.log("queueing", id, path);
        imageQueue.add({ id, path });
      } catch (e) {
        console.error(e);
      }
    },
    {
      concurrency: 5,
    }
  );
  res.json({ message: "Images stored in the database" });
});

// search for images with a text query

function cosineSimilarity(A, B) {
  if (A.length !== B.length) throw new Error("A.length !== B.length");
  let dotProduct = 0,
    mA = 0,
    mB = 0;
  for (let i = 0; i < A.length; i++) {
    dotProduct += A[i] * B[i];
    mA += A[i] * A[i];
    mB += B[i] * B[i];
  }
  mA = Math.sqrt(mA);
  mB = Math.sqrt(mB);
  let similarity = dotProduct / (mA * mB);
  return similarity;
}

router.get("/images", async (req, res) => {
  const { query } = req.query;
  const textInputs = await tokenizer(query);
  let { text_embeds } = await textModel(textInputs);
  const textEmbeddings = Array.from(text_embeds.data);
  const results = await db
    .select(["path", "embeddings"])
    .from("images")
    .orderBy(db.cosineDistance("embeddings", textEmbeddings))
    .limit(30);
  // add the cosine distance to the results
  results.forEach((result) => {
    const imageEmbeddings = pgvector.fromSql(result.embeddings);
    result.cosineDistance = cosineSimilarity(textEmbeddings, imageEmbeddings);
  });
  res.json(results);
});

// find very different images from the database
// subtract the means
// find a way to visualize the embeddings
// create embedding input

router.get("/", (req, res) => {
  res.json({
    message: "API - 👋🌎🌍🌏",
  });
});

router.post("/images", async (req, res) => {
  const data = await downloadAll("./public");
  console.log(data);
});

export default router;
