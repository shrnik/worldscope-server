// do a fetch to the faa images api and return the images
import axios from "axios";
import fs from "fs";
import path from "path";
import dotenv from "dotenv";
import { CamDataType } from "../types/cameraData";
dotenv.config();

const FAA_API_URL = "https://weathercams.faa.gov/api/redistributable/sites";
const HEADERS = {
  Authorization: `Bearer ${process.env.FAA_API_KEY}`,
};
const getFaaRawData = async () => {
  const res = await axios.get(FAA_API_URL, {
    headers: HEADERS,
  });
  const sites = res?.data?.payload;
  return sites as Promise<any[]>;
};

const getFaaImages = async () => {
  const sites = await getFaaRawData();
  const faaImages = sites
    .map((site) => {
      if (!site.cameras) return [];
      const cams: CamDataType[] = site?.cameras.map((camera: any) => {
        return {
          cameraName: `${site.siteName} ${camera.cameraDirection} ${
            site.operatedBy || ""
          }`,
          url: camera.currentImageUri,
          source: "faa.gov",
          lat: site.latitude,
          long: site.longitude,
          refreshRate: "10 min",
        };
      });
      return cams || [];
    })
    .flat();
  return faaImages;
};

export default getFaaImages;
