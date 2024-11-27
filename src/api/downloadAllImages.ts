import axios from "axios";
import contants from "../constants";
import Bluebird from "bluebird";
import downloadImage from "./download-image";
import imageQueue from "./queue";
import db from "./db";
import dotenv from "dotenv";
import path from "path";
const { sheetUrl } = contants;
dotenv.config();

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

const downloadAllImages = async () => {
  const images = await getImages();
  await Bluebird.map(
    images.splice(0, 10),
    async (image) => {
      try {
        const downloaded = await downloadImage(image.cameraId, image.url);
        console.log(`Downloaded image for ${image.cameraId}`);
        if (downloaded) {
          const record = await db("images_archive")
            .insert({
              camera_id: image.cameraId,
              url: downloaded.filePath,
            })
            .returning("id");
          const queueRecord = {
            camera_id: image.cameraId,
            url: path.join(
              process.env.IMAGES_BASE_URL as string,
              downloaded.filePath
            ),
            imageId: record[0].id,
            isArchive: true,
          };
          imageQueue.add("imageProcessor", queueRecord);
        }
      } catch (e) {
        console.error(e);
        console.error(`Failed to download image for ${image.cameraId}`);
      }
    },
    { concurrency: 10 }
  );
};

export default downloadAllImages;
