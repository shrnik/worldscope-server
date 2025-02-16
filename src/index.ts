import app from "./app";
// dotenv

import { config } from "dotenv";
import path from "path";

config({ path: path.join(__dirname, ".env") });

const port = process.env.PORT || 5000;

app.listen(port, () => {
  /* eslint-disable no-console */
  console.log(`Listening: http://localhost:${port}`);
  /* eslint-enable no-console */
});
