import dotenv from "dotenv";
dotenv.config();

const connection = {
  host: process.env.REDIS_HOST,
  port: 6379,
  password: process.env.REDIS_PASSWORD,
};

export default connection;
