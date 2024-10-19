import express from "express";

import pgvector from "pgvector/knex";

import {
  AutoTokenizer,
  CLIPTextModelWithProjection,
} from "@xenova/transformers";

import axios from "axios";
import Bluebird from "bluebird";
import constants from "../constants.mjs";
import db from "./db.mjs";
import downloadAll from "./downloader.mjs";
import imageQueue from "./queue.mjs";
import Cron from "node-cron";

const { sheetUrl } = constants;

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
    table.string("url");
    table.string("camera_id");
    table.vector("embedding", 512);
    table.timestamps();
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

const getImages = async () => {
  const res = await axios.get(sheetUrl);
  const [header, ...data] = Object.values(res.data.values);
  const imageMetas = data.map((d, index) => {
    return {
      url: d[1],
      cameraId: index,
      cameraName: d[0],
    };
  });
  return imageMetas;
};

const queueimages = async () => {
  const images = await getImages();
  await Bluebird.map(
    images,
    async ({ url, cameraId }) => {
      try {
        imageQueue.add({ url, cameraId });
      } catch (e) {
        console.error(e);
      }
    },
    {
      concurrency: 100,
    }
  );
};

// use node cron to schedule the job to run every 15 mins
Cron.schedule("*/15 5-22 * * *", async () => {
  if (process.env.NODE_ENV === "production") {
    console.log("Queueing images using cron");
    await queueimages();
  }
});

router.post("/images", async (req, res) => {
  await queueimages();
  res.json({ message: "Images queued for embeddings" });
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
  try {
    const textInputs = await tokenizer(query);
    let { text_embeds } = await textModel(textInputs);
    const textEmbeddings = Array.from(text_embeds.data);
    const results = await db
      .select(["url", "embedding", "created_at"])
      .from("images")
      .orderBy(db.cosineDistance("embedding", textEmbeddings))
      .limit(30);
    // add the cosine distance to the results
    results.forEach((result) => {
      const imageEmbeddings = pgvector.fromSql(result.embedding);
      result.cosineDistance = cosineSimilarity(textEmbeddings, imageEmbeddings);
    });
    res.json(results);
  } catch (e) {
    res.sendStatus(400).statusMessage(e.message);
  }
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
