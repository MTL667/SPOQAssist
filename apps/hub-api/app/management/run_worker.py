"""Entrypoint for the precompute worker container.

Usage:
    python -m app.management.run_worker [--batch-size 4] [--poll-interval 2]
"""

from __future__ import annotations

import argparse
import logging

from app.services.precompute import run_worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="SpoqSense precompute worker")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    run_worker(batch_size=args.batch_size, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
