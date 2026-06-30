"""Run the bucket cleanup stage on HF Jobs and wait for it.

Submits the CPU cleanup job (prune images not referenced by the current
embeddings.parquet) and blocks until it finishes, exiting non-zero on failure.
Assumes the embed stage has already written the embeddings. Config is read from the
environment via app.settings.
"""

from __future__ import annotations

import sys

from app import hf_jobs


def main() -> int:
    job_id = hf_jobs.trigger_cleanup_job()
    print(f"cleanup job: {job_id}", flush=True)
    final = hf_jobs.poll_until_done(job_id)
    if final != "COMPLETED":
        print(f"cleanup job {job_id} ended as {final}", file=sys.stderr)
        return 1
    print("cleanup complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
