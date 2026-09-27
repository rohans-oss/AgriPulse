"""Fetch now from the command line (cron / Windows Task Scheduler friendly).

    python -m app.ingest weather                 # every organization with located warehouses
    python -m app.ingest weather --org <slug>    # one organization
    python -m app.ingest market                  # the shared public mandi-price fetch
    python -m app.ingest all

Unlike the scheduler (python -m app.scheduler), this fetches immediately even if not due.
Exit code 1 if any fetch failed.
"""

import argparse
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import IngestionRun, Organization, Warehouse
from app.models.enums import RunStatus
from app.services.data.connectors import execute_run, is_configured
from app.services.data.scheduler import Job, start_job
from app.services.data.sources import OGD_MANDI, OPEN_METEO, sync_sources

TARGETS = {"weather": [OPEN_METEO], "market": [OGD_MANDI], "all": [OPEN_METEO, OGD_MANDI]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--org", help="organization slug (Settings → Workspace ID); weather only")
    args = parser.parse_args()

    jobs: list[Job] = []
    with SessionLocal() as db:
        sync_sources(db)
        org_ids = None
        if args.org:
            org = db.scalar(select(Organization).where(Organization.slug == args.org))
            if org is None:
                print(f"No organization with slug '{args.org}'", file=sys.stderr)
                return 2
            org_ids = [org.id]
        for key in TARGETS[args.target]:
            ok, msg = is_configured(key)
            if not ok:
                print(f"{key}: skipped — {msg}")
                continue
            if key == OPEN_METEO:
                ids = org_ids or db.scalars(select(Warehouse.organization_id).where(
                    Warehouse.latitude.is_not(None)).distinct()).all()
                if not ids:
                    print(f"{key}: skipped — no organization has warehouses with coordinates")
                jobs += [Job(key, o) for o in ids]
            else:
                jobs.append(Job(key, None))
        runs = [(j, start_job(db, j).id) for j in jobs]

    exit_code = 0
    for job, run_id in runs:
        execute_run(SessionLocal, run_id)
        with SessionLocal() as db:
            run = db.get(IngestionRun, run_id)
            who = "public" if job.organization_id is None else str(job.organization_id)[:8]
            print(f"{job.source_key} [{who}]: {run.status.value} — received {run.rows_received}, new {run.rows_inserted}, "
                  f"updated {run.rows_updated}, duplicate {run.rows_duplicate}, rejected {run.rows_rejected}"
                  + (f" — {run.error_kind}: {run.error_message}" if run.error_message else ""))
            if run.status == RunStatus.FAILED:
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
