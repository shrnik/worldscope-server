import express from "express";

import pgvector from "pgvector/knex";

import axios from "axios";
import Bluebird from "bluebird";
import constants from "../constants";
import cosineSimilarity from "../utils/cosine-similarity";
import { getFilePath } from "../utils/helpers";
import db from "./db";
import { saveImage } from "./download-image";
import downloadAll from "./downloader";
import { makeImageEmbedding } from "./embeddings";
import imageQueue from "./queue";
import makeTextEmbedding from "./text-embeddings";
import fs from "fs";
import { getImages } from "./downloadAllImages";

const { sheetUrl } = constants;

const router = express.Router();

const TABLE_NAME = "images_siglip";

// create a table in the database to store the image features using Knex
db.schema
  .raw("CREATE EXTENSION IF NOT EXISTS vector")
  .createTableIfNotExists("TABLE_NAME", (table) => {
    table.increments("id");
    table.string("url");
    table.string("camera_id");
    (table as any).vector("embedding", 768);
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

const queueimages = async () => {
  const images = await getImages();
  await Bluebird.map(
    images,
    async ({ url, ...extra }, cameraId) => {
      const { filePath, internalPath } = getFilePath(cameraId, url);
      try {
        await saveImage(url, filePath);
        const newUrl = new URL(
          internalPath,
          process.env.IMAGES_BASE_URL as string
        );
        imageQueue.add(
          "imageProcessor",
          { url: newUrl.toString(), cameraId, metadata: extra },
          { removeOnComplete: true, deduplication: { id: cameraId.toString() } }
        );
      } catch (e) {
        // remove file if it exists so that there is no stale data
        if (fs.existsSync(filePath)) {
          fs.unlink(filePath, (err) => {
            if (err) {
              console.error("Error deleting file:", err);
              return;
            }
            console.log("File deleted successfully");
          });
        }

        // remove entry for the image from the database
        await db(TABLE_NAME).where("url", url).del();
        console.error(e);
      }
    },
    {
      concurrency: 10,
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
  queueimages();
  res.json({ message: "Images will be queued for embeddings" });
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

router.post("/embeddings/text", async (req, res) => {
  try {
    const { text } = req.body;
    const embedding = await makeTextEmbedding(text);
    res.json({ text, embedding });
  } catch (e: any) {
    res.status(400).send(e.message);
  }
});

router.get("/images", async (req, res) => {
  const { query } = req.query;
  try {
    const textEmbeddings = await makeTextEmbedding(query as string);
    if (!textEmbeddings) {
      throw new Error("Invalid query");
    }
    const results = await db
      .select(["url", "embedding", "created_at", "updated_at", "metadata"])
      .from(TABLE_NAME)
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
