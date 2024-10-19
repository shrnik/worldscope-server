module.exports = {
  apps: [
    {
      name: "app1",
      script: "./index.mjs",
      env_production: {
        NODE_ENV: "production",
        PORT: 8000,
        POSTGRES_PASSWORD: "new_password",
        POSTGRES_USER: "postgres",
      },
    },
  ],
};
