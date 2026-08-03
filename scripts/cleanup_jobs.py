from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from print_preflight.job_store import JobStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired MVP PDF artifacts")
    parser.add_argument("--data-dir", default="var/mvp")
    args = parser.parse_args()
    deleted = JobStore(Path(args.data_dir)).cleanup_expired()
    print(f"expired_jobs_deleted={deleted}")


if __name__ == "__main__":
    main()
