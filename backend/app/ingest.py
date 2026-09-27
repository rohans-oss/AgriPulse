"""Run ingestion from the command line (for cron / Windows Task Scheduler).

    python -m app.ingest weather --org agriflow-demo-foods
    python -m app.ingest market  --org agriflow-demo-foods
    python -m app.ingest all     --org agriflow-demo-foods

Suggested schedule: weather every hour, market prices once a day in the evening (IST),
after mandis have reported.
"""

import argparse
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import IngestionRun, Organization
from app.models.enums import RunTrigger
from app.services.data.connectors import execute_run, is_configured
from app.services.data.sources import OGD_MANDI, OPEN_METEO, get_source, sync_sources

TARGETS = {"weather": [OPEN_METEO], "market": [OGD_MANDI], "all": [OPEN_METEO, OGD_MANDI]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--org", required=True, help="organization slug (Settings → Workspace ID)")
    args = parser.parse_args()

    exit_code = 0
    with SessionLocal() as db:
        sync_sources(db)
        org = db.scalar(select(Organization).where(Organization.slug == args.org))
        if org is None:
            print(f"No organization with slug '{args.org}'", file=sys.stderr)
            return 2
        run_ids = []
        for key in TARGETS[args.target]:
            ok, msg = is_configured(key)
            if not ok:
                print(f"{key}: skipped — {msg}")
                continue
            run = IngestionRun(source_id=get_source(db, key).id, organization_id=org.id,
                               trigger=RunTrigger.SCHEDULED, params={})
            db.add(run)
            db.commit()
            run_ids.append((key, run.id))

    for key, run_id in run_ids:
        execute_run(SessionLocal, run_id)
        with SessionLocal() as db:
            run = db.get(IngestionRun, run_id)
            print(f"{key}: {run.status.value} — inserted {run.rows_inserted}, updated {run.rows_updated}, "
                  f"unchanged {run.rows_unchanged}, rejected {run.rows_rejected}"
                  + (f" — {run.error_message}" if run.error_message else ""))
            if run.status.value == "FAILED":
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
