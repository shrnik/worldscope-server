import db from "./db";
process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";

const main = async () => {
  await db.schema
    .raw("CREATE EXTENSION IF NOT EXISTS vector")
    .createTableIfNotExists("images", (table) => {
      table.increments("id");
      table.string("url");
      table.string("camera_id");
      (table as any).vector("embedding", 512);
      table.timestamps();
    })
    .then(() => {
      console.log("table created");
    })
    .catch((err) => {
      console.error(err);
    });

  await db.schema.alterTable("images", function (table) {
    table.index(
      (db as any).raw("embeddings vector_l2_ops"),
      "images_hnsw_index",
      "hnsw"
    );
  });
};

main();
