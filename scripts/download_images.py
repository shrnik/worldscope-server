"""Run the image-download stage on HF Jobs and wait for it.

Submits the CPU download job (fetch camera list + snapshots -> bucket + manifest)
and blocks until it finishes, exiting non-zero on failure. Config is read from the
environment via app.settings.
"""

from __future__ import annotations

import sys

from app import hf_jobs


def main() -> int:
    job_id = hf_jobs.trigger_download_job()
    print(f"download job: {job_id}", flush=True)
    final = hf_jobs.poll_until_done(job_id)
    if final != "COMPLETED":
        print(f"download job {job_id} ended as {final}", file=sys.stderr)
        return 1
    print("download complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
