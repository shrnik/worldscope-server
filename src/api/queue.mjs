import { Queue } from "bullmq";
import dotenv from "dotenv";
dotenv.config();

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const connection = {
  host: process.env.REDIS_HOST,
  port: 6379,
  password: process.env.REDIS_PASSWORD,
};

const imageQueue = new Queue("images", { connection });

export default imageQueue;
