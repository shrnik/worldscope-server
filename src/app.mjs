import express from "express";
import morgan from "morgan";
import helmet from "helmet";
import cors from "cors";
import middlewares from "./middlewares/index.mjs";
import api from "./api/index.mjs";

import dotenv from "dotenv";
dotenv.config();

const app = express();

app.use(morgan("dev"));
app.use(helmet());
app.use(
  cors({
    origin: "http://localhost:3000",
  })
);
app.use(express.json());

app.get("/", (req, res) => {
  res.json({
    message: "🦄🌈✨👋🌎🌍🌏✨🌈🦄",
  });
});

app.use("/api/v1", api);
// serve all the files inside public/images

// set cors headers
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("cross-origin-resource-policy", "cross-origin");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
  next();
});
app.use("/images", express.static("public/images"));

app.use(middlewares.notFound);
app.use(middlewares.errorHandler);

export default app;
