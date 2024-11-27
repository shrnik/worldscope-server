module.exports = {
  apps: [
    {
      name: "workers",
      script: "./dist/api/worker.js",
      exec_mode: "cluster",
      instances: 2,
      max_memory_restart: "4G",
      node_args: ["--max_old_space_size=2048"],
    },
    {
      name: "results-worker",
      script: "./dist/api/results-worker.js",
      exec_mode: "fork",
      instances: 1,
      node_args: ["--max_old_space_size=2048"],
    },
  ],
};
