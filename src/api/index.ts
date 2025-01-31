import express from "express";

import pgvector from "pgvector/knex";

import axios from "axios";
import Bluebird from "bluebird";
import constants from "../constants";
import db from "./db";
import downloadAll from "./downloader";
import imageQueue from "./queue";
import { makeImageEmbedding } from "./embeddings";
import makeTextEmbedding from "./text-embeddings";

const { sheetUrl } = constants;

const router = express.Router();

// create a table in the database to store the image features using Knex
db.schema
  .raw("CREATE EXTENSION IF NOT EXISTS vector")
  .createTableIfNotExists("images", (table) => {
    table.increments("id");
    table.string("url");
    table.string("camera_id");
    (table as any).vector("embedding", 512);
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
//Alter table images add constraint unique_cameraId unique (cameraId);
// await db.schema.alterTable("images", function (table) {
//   table.unique("camera_id", {
//     indexName: "unique_camera_id",
//   });
// });

const getImages = async () => {
  const res = await axios.get(sheetUrl);
  const [header, ...data] = Object.values(res.data.values) as string[][];
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
        imageQueue.add(
          "imageProcessor",
          { url, cameraId },
          { removeOnComplete: true, deduplication: { id: cameraId.toString() } }
        );
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
// Cron.schedule("*/15 5-22 * * *", async () => {
//   if (process.env.NODE_ENV === "production") {
//     console.log("Queueing images using cron");
//     await queueimages();
//   }
// });

router.post("/images", async (req, res) => {
  await queueimages();
  res.json({ message: "Images queued for embeddings" });
});

router.post("/embeddings/image", async (req, res) => {
  try {
    const { url } = req.body;
    const embedding = await makeImageEmbedding(url);
    res.json({ url, embedding });
  } catch (e: any) {
    res.status(400).send(e.message);
  }
});

// search for images with a text query

function cosineSimilarity(A: number[], B: number[]) {
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
    const textEmbeddings = await makeTextEmbedding(query as string);
    if (!textEmbeddings) {
      throw new Error("Invalid query");
    }
    const results = await db
      .select(["url", "embedding", "created_at", "updated_at"])
      .from("images")
      .orderBy((db as any).cosineDistance("embedding", textEmbeddings))
      .limit(50);
    // add the cosine distance to the results
    results.forEach((result) => {
      const imageEmbeddings = pgvector.fromSql(result.embedding);
      result.cosineDistance = cosineSimilarity(textEmbeddings, imageEmbeddings);
    });
    res.json(results);
  } catch (e: any) {
    res.status(400).send(e.message);
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
