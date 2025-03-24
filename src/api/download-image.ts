// given a list of cameras and urls to download images from, download the images and save them to the database

import { RawImage } from "@huggingface/transformers";
import * as fs from "fs";
import * as path from "path";
import { isValidExt } from "../utils/helpers";

async function downloadImage(
  cameraId: number | string,
  url: string,
  fPath?: string
) {
  try {
    const rawImage = await RawImage.fromURL(url);
    const timestamp = new Date().toISOString();

    // Create a folder structure based on the cameraId and timestamp
    // path looks like: images/YYYY-MM-DD/hour/cameraId/timestamp.jpg
    const internalPath = fPath
      ? fPath
      : path.join(
          timestamp.split("T")[0],
          timestamp.split("T")[1].split(":")[0],
          cameraId.toString()
        );
    const folderPath = path.resolve(__dirname, "../..", "images", internalPath);
    fs.mkdirSync(folderPath, { recursive: true });

    // Save the image to the folder
    const filePath = path.join(folderPath, `${timestamp}.jpg`);
    await rawImage.save(filePath);
    // save the path to the database
    return { cameraId, url, timestamp, filePath: filePath.split("images/")[1] };
  } catch (e) {
    // delete the file in that location
    console.error(e);
  }
}

async function saveImage(url: string, filePath: string) {
  const rawImage = await RawImage.fromURL(url);
  await rawImage.save(filePath);
}
export default downloadImage;
export { downloadImage, saveImage, isValidExt };
