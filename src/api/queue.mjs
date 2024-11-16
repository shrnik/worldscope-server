import { Queue } from "bullmq";
import connection from "./redis-connection.mjs";

process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const imageQueue = new Queue("images", { connection });

const resultsQueue = new Queue("results", { connection });

export default imageQueue;

export { resultsQueue, imageQueue };
