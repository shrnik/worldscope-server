module.exports = {
  apps: [
    {
      name: "app1",
      script: "./src/index.mjs",
      env: {
        NODE_ENV: "production",
        PORT: 8000,
        POSTGRES_PASSWORD: "new_password",
        POSTGRES_USER: "postgres",
      },
    },
    {
      name: "workers",
      script: "./src/api/queue.mjs",
      exec_mode: "cluster",
      instances: 1,
      node_args: ["--max_old_space_size=2048"],
    },
  ],
};
