module.exports = {
  apps: [
    {
      name: "api-app",
      script: "./dist/index.js",
      env: {
        NODE_ENV: "production",
        PORT: 8000,
        WORKER_DISABLED: true,
      },
    },
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
  ],
};
