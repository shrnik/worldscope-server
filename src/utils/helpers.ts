import fs from "fs";
import path from "path";

const isValidExt = (ext?: string) =>
  ext && ["jpg", "jpeg", "png", "gif"].includes(ext);

const getFilePath = (cameraId: number | string, url: string) => {
  const timestamp = new Date().toISOString();
  const tempExt = url.split(".").pop();
  const ext = isValidExt(tempExt) ? tempExt : "jpg";

  // Create a folder structure based on the cameraId and timestamp
  // path looks like: images/YYYY-MM-DD/hour/cameraId/timestamp.jpg
  const internalPath = path.join(cameraId.toString(), `default.${ext}`);
  const filePath = path.resolve(__dirname, "../..", "images", internalPath);
  fs.mkdirSync(filePath, { recursive: true });

  // Save the image to the folder
  return {
    filePath,
    internalPath,
  };
};

export { isValidExt, getFilePath };
