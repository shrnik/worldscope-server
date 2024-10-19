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
  ],
};
