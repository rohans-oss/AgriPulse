"""Market price normalization, validation (data-quality checks) and idempotent upsert.

Used by both the data.gov.in connector and CSV uploads, so every price row passes the
same checks no matter where it came from.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionIssue, IngestionRun, MarketPrice
from app.models.enums import IssueSeverity
from app.services.data.freshness import today_ist

MAX_PLAUSIBLE_PRICE = Decimal("1000000")  # ₹/quintal; anything above is a data error
JUMP_FACTOR = Decimal("3")  # modal price ×3 or ÷3 vs previous report → warning

ALIASES: dict[str, tuple[str, ...]] = {
    "state": ("state", "state_name"),
    "district": ("district", "district_name"),
    "market": ("market", "market_name", "market_center", "apmc", "apmc_name"),
    "commodity": ("commodity", "commodity_name"),
    "variety": ("variety", "variety_name"),
    "grade": ("grade",),
    "arrival_date": ("arrival_date", "price_date", "reported_date", "date"),
    "min_price": ("min_price", "minimum_price", "min_price_rs_quintal", "min_price_rs"),
    "max_price": ("max_price", "maximum_price", "max_price_rs_quintal", "max_price_rs"),
    "modal_price": ("modal_price", "modal_price_rs_quintal", "modal_price_rs"),
}
REQUIRED = ("state", "market", "commodity", "arrival_date", "modal_price")
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d/%m/%y")


def normalize_header(name: str) -> str:
    n = name.strip().lower().replace("_x0020_", "_")
    n = re.sub(r"[^a-z0-9]+", "_", n)
    return n.strip("_")


def header_map(headers) -> dict[str, str]:
    """Map raw header -> canonical field for the headers we recognise."""
    lookup = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}
    out = {}
    for h in headers:
        canon = lookup.get(normalize_header(h))
        if canon and canon not in out.values():
            out[h] = canon
    return out


def parse_date(value) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_price(value) -> Decimal | None:
    if value is None:
        return None
    s = re.sub(r"[₹,\s]|rs\.?", "", str(value).strip(), flags=re.I)
    if s in ("", "-", "NA", "na", "N/A"):
        return None
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"'{value}' is not a number") from None


@dataclass
class RowResult:
    clean: dict | None
    issues: list[dict] = field(default_factory=list)


def _issue(row, field_, severity, code, message, raw):
    return {"row_number": row, "field": field_, "severity": severity, "code": code, "message": message, "raw": raw}


def validate_row(raw: dict, row_number: int, hmap: dict[str, str] | None = None, today: date | None = None) -> RowResult:
    today = today or today_ist()
    hmap = hmap if hmap is not None else header_map(raw.keys())
    data = {canon: raw.get(orig) for orig, canon in hmap.items()}
    issues: list[dict] = []
    raw_json = {str(k): (None if v is None else str(v)) for k, v in raw.items()}

    def err(f, code, msg):
        issues.append(_issue(row_number, f, IssueSeverity.ERROR, code, msg, raw_json))

    def warn(f, code, msg):
        issues.append(_issue(row_number, f, IssueSeverity.WARNING, code, msg, raw_json))

    text = {k: (str(data.get(k)).strip() if data.get(k) not in (None, "") else "") for k in
            ("state", "district", "market", "commodity", "variety", "grade")}
    for f in REQUIRED:
        if f in text and not text[f]:
            err(f, "MISSING", f"{f.replace('_', ' ').title()} is required")

    arrival = None
    if data.get("arrival_date") in (None, ""):
        err("arrival_date", "MISSING", "Arrival date is required")
    else:
        arrival = parse_date(data["arrival_date"])
        if arrival is None:
            err("arrival_date", "INVALID_DATE", f"Unrecognised date '{data['arrival_date']}'")
        elif arrival > today + timedelta(days=1):
            err("arrival_date", "FUTURE_DATE", f"Arrival date {arrival} is in the future")

    prices: dict[str, Decimal | None] = {}
    for f in ("min_price", "max_price", "modal_price"):
        try:
            prices[f] = parse_price(data.get(f))
        except ValueError as e:
            err(f, "NOT_A_NUMBER", str(e))
            prices[f] = None
            continue
        p = prices[f]
        if p is not None and p <= 0:
            err(f, "NON_POSITIVE", f"{f.replace('_', ' ')} must be greater than zero")
        elif p is not None and p > MAX_PLAUSIBLE_PRICE:
            err(f, "IMPLAUSIBLE", f"{f.replace('_', ' ')} ₹{p}/quintal is implausibly high")
    if prices.get("modal_price") is None and not any(i["field"] == "modal_price" for i in issues):
        err("modal_price", "MISSING", "Modal price is required")

    lo, hi, modal = prices.get("min_price"), prices.get("max_price"), prices.get("modal_price")
    if lo and hi and lo > hi:
        err("min_price", "MIN_ABOVE_MAX", f"Min price ₹{lo} is above max price ₹{hi}")
    elif modal and lo and hi and not (lo <= modal <= hi):
        warn("modal_price", "MODAL_OUTSIDE_RANGE", f"Modal ₹{modal} is outside the min–max range ₹{lo}–₹{hi}")

    if any(i["severity"] == IssueSeverity.ERROR for i in issues):
        return RowResult(None, issues)
    clean = {**text, "arrival_date": arrival, "min_price": lo, "max_price": hi, "modal_price": modal}
    return RowResult(clean, issues)


def dedupe_key(source_id: uuid.UUID, org_id: uuid.UUID | None, row: dict) -> str:
    parts = [str(source_id), str(org_id or "public")] + [
        row[k].strip().lower() for k in ("state", "district", "market", "commodity", "variety", "grade")
    ] + [row["arrival_date"].isoformat()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: int = 0


def _previous_modal(db: Session, source_id, org_id, row) -> Decimal | None:
    stmt = (
        select(MarketPrice.modal_price)
        .where(
            MarketPrice.source_id == source_id,
            MarketPrice.organization_id.is_(None) if org_id is None else MarketPrice.organization_id == org_id,
            MarketPrice.market == row["market"],
            MarketPrice.commodity == row["commodity"],
            MarketPrice.variety == row["variety"],
            MarketPrice.grade == row["grade"],
            MarketPrice.arrival_date < row["arrival_date"],
        )
        .order_by(MarketPrice.arrival_date.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def upsert_prices(db: Session, run: IngestionRun, rows: list[tuple[int, dict]], org_id, fetched_at: datetime) -> UpsertStats:
    """Insert new rows, update changed ones, count identical ones. Adds jump warnings."""
    stats = UpsertStats()
    keyed = {}
    for row_number, row in rows:
        keyed[dedupe_key(run.source_id, org_id, row)] = (row_number, row)  # last duplicate in a batch wins
    existing: dict[str, MarketPrice] = {}
    keys = list(keyed)
    for i in range(0, len(keys), 500):
        for mp in db.scalars(select(MarketPrice).where(MarketPrice.dedupe_key.in_(keys[i:i + 500]))):
            existing[mp.dedupe_key] = mp

    for key, (row_number, row) in keyed.items():
        prev = _previous_modal(db, run.source_id, org_id, row)
        if prev and row["modal_price"] and (row["modal_price"] > prev * JUMP_FACTOR or row["modal_price"] * JUMP_FACTOR < prev):
            stats.warnings += 1
            db.add(IngestionIssue(run_id=run.id, row_number=row_number, field="modal_price",
                                  severity=IssueSeverity.WARNING, code="UNUSUAL_CHANGE",
                                  message=f"Modal ₹{row['modal_price']} vs ₹{prev} on the previous report for "
                                          f"{row['commodity']} at {row['market']}",
                                  raw={k: str(v) for k, v in row.items()}))
        mp = existing.get(key)
        values = {"min_price": row["min_price"], "max_price": row["max_price"], "modal_price": row["modal_price"]}
        if mp is None:
            db.add(MarketPrice(dedupe_key=key, organization_id=org_id, source_id=run.source_id, run_id=run.id,
                               fetched_at=fetched_at, **{k: row[k] for k in (
                                   "state", "district", "market", "commodity", "variety", "grade", "arrival_date")},
                               **values))
            stats.inserted += 1
        elif any(getattr(mp, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(mp, k, v)
            mp.run_id, mp.fetched_at = run.id, fetched_at
            stats.updated += 1
        else:
            mp.fetched_at = fetched_at
            stats.unchanged += 1
    return stats


def record_issues(db: Session, run: IngestionRun, issues: list[dict]) -> None:
    for i in issues:
        db.add(IngestionIssue(run_id=run.id, **i))
