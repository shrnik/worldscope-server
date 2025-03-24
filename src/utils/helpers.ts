import fs from "fs";
import path from "path";

const isValidExt = (ext?: string) =>
  ext && ["jpg", "jpeg", "png", "gif"].includes(ext);

const getFilePath = (cameraId: number | string, url: string) => {
  const timestamp = new Date().toISOString();
  const tempExt = url.split(".").pop();
  const ext = isValidExt(tempExt) ? tempExt : "jpg";

  // Create a folder structure based on the cameraId
  const internalPath = path.join(cameraId.toString(), `default.${ext}`);
  const folderPath = path.resolve(
    __dirname,
    "../..",
    "images",
    cameraId.toString()
  );

  fs.mkdirSync(folderPath, { recursive: true });

  const filePath = path.resolve(__dirname, "../..", "images", internalPath);
  // check if the folder exists

  // Save the image to the folder
  return {
    filePath,
    internalPath,
  };
};

export { isValidExt, getFilePath };
