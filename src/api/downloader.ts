process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";
import axios from "axios";
import fs from "fs";
import bluebird from "bluebird";
import path from "path";

const sheetUrl =
  "https://sheets.googleapis.com/v4/spreadsheets/1_tbi4WTx9qGErN-2cvYvEd3qeJxgzd_9N9HJWWPD7SA/values/Main?alt=json&key=AIzaSyA6pmS1gW0a3dWzxdYOfo-sE5hmmvGrW8M";

const isValidExt = (ext?: string) =>
  ext && ["jpg", "jpeg", "png", "gif"].includes(ext);

const downloadAll = async (pathName: string) => {
  const res = await axios.get(sheetUrl);
  console.log(typeof res.data.values);
  const [header, ...data] = Object.values(res.data.values) as string[][];
  const timeStamp = new Date().getTime();
  const imageMetas = data.map((d, index) => {
    return {
      url: d[1],
      cameraId: index,
      cameraName: d[0],
      timeStamp,
    };
  });
  const ress = await bluebird.map(
    imageMetas,
    async ({ url, ...meta }) => {
      try {
        const response = await axios({
          method: "GET",
          url,
          responseType: "stream",
          timeout: 10000,
        });

        // create a directory using temestamp
        // if directory does not exist create one using timestamp
        if (!fs.existsSync(path.resolve(pathName, "images"))) {
          fs.mkdirSync(path.resolve(pathName, "images"));
        }

        const tempExt = url.split(".").pop();
        const ext = isValidExt(tempExt) ? tempExt : "jpg";

        const dir = path.resolve(
          pathName,
          "images",
          `${timeStamp}-${meta.cameraId}.${ext}`
        );
        response.data.pipe(fs.createWriteStream(dir));
        const result = await new Promise((resolve, reject) => {
          response.data.on("end", () => {
            console.log("download complete");
            resolve({
              ...meta,
              path: dir,
            });
          });
          setTimeout(() => {
            console.error("download timeout");
            reject(false);
          }, 20000);
          response.data.on("error", (err: any) => {
            console.error("download error", err);
            reject(false);
          });
        });
        return result;
      } catch (e) {
        console.error(e);
        console.count("error");
      }
    },
    { concurrency: 25 }
  );
  return ress.filter((r) => !!r);
};

export default downloadAll;
