import app from "./app";
// dotenv

import { config } from "dotenv";
import path from "path";
import cron from "node-cron";
import downloadAllImages from "./api/downloadAllImages";

config({ path: path.join(__dirname, ".env") });

const port = process.env.PORT || 5000;

app.listen(port, () => {
  /* eslint-disable no-console */
  console.log(`Listening: http://localhost:${port}`);
  /* eslint-enable no-console */
});

cron.schedule("0 */2 * * *", async () => {
  downloadAllImages();
});
