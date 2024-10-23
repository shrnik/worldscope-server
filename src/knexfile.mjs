export default {
  development: {
    client: "pg",
    connection: {
      user: "doadmin",
      password: "",
      host: "db-postgresql-nyc3-26124-do-user-18091142-0.k.db.ondigitalocean.com",
      port: "25060",
      database: "defaultdb",
      ssl: true,
    },
    migrations: {
      directory: "./migrations",
    },
    seeds: {
      directory: "./seeds",
    },
  },
};
