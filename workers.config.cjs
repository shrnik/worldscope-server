module.exports = {
  apps: [
    {
      name: "workers",
      script: "./src/api/worker.mjs",
      exec_mode: "cluster",
      instances: 2,
      node_args: ["--max_old_space_size=2048"],
    },
    {
      name: "results-worker",
      script: "./src/api/results-worker.mjs",
      exec_mode: "fork",
      instances: 1,
      node_args: ["--max_old_space_size=2048"],
    },
  ],
};
