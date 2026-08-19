from __future__ import annotations

import argparse
import os
import socket
import time

from app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker local Vector Hub")
    parser.add_argument("--once", action="store_true", help="Traite au plus un job puis s'arrête")
    parser.add_argument("--poll", type=float, default=1.0, help="Intervalle de polling en secondes")
    args = parser.parse_args()

    app = create_app()
    jobs = app.extensions["job_service"]
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    jobs.resume_interrupted()

    while True:
        processed = jobs.run_next(worker_id)
        if args.once:
            break
        if not processed:
            time.sleep(args.poll)


if __name__ == "__main__":
    main()
