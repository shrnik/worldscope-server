import { Queue, Worker } from "bullmq";
import dotenv from "dotenv";
dotenv.config();
import { dirname } from "path";
import pgVector from "pgvector/knex";
import { fileURLToPath } from "url";
import db from "./db.mjs";
import imageWorker from "./image-worker.mjs";

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const connection = {
  host: process.env.REDIS_HOST,
  port: 6379,
  password: process.env.REDIS_PASSWORD,
};

const imageQueue = new Queue("images", { connection });

export default imageQueue;
