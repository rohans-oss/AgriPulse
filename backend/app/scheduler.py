"""Automatic ingestion worker.

    python -m app.scheduler            # run forever, checking every 60 s
    python -m app.scheduler --once     # one tick (for cron / Windows Task Scheduler)

Run it next to the API (a second terminal, a systemd service, or a scheduled task).
What is due is computed from the ingestion history, so restarts never double-fetch.
"""

import argparse
import logging
import time

from app.core.database import SessionLocal
from app.services.data.scheduler import run_due
from app.services.data.sources import sync_sources
from app.services.rbac import sync_rbac

log = logging.getLogger("agriflow.scheduler")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="run one tick and exit")
    parser.add_argument("--interval", type=int, default=60, help="seconds between ticks (default 60)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with SessionLocal() as db:
        sync_rbac(db)
        sync_sources(db)

    while True:
        try:
            started = run_due(SessionLocal)
            if started:
                log.info("Started and finished %d ingestion run(s)", len(started))
        except Exception:  # noqa: BLE001 - keep the worker alive; the failure is logged
            log.exception("Scheduler tick failed")
        if args.once:
            return
        time.sleep(max(args.interval, 10))


if __name__ == "__main__":
    main()
