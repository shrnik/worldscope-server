import knex from "knex";
import knexConfig from "../knexfile.mjs";
const db = knex(knexConfig.development);
export default db;
