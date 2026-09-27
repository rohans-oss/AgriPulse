"""Market price normalization, validation (data-quality checks) and idempotent upsert.

Used by both the data.gov.in connector and CSV uploads, so every price row passes the
same checks no matter where it came from. Every stored row keeps its provenance:
source dataset, endpoint, source record id, the raw record, validation status and notes.
"""

import hashlib
import json
import re
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionIssue, IngestionRun, MarketPrice
from app.models.enums import IssueSeverity, ValidationStatus
from app.services.data.freshness import today_ist

MAX_PLAUSIBLE_PRICE = Decimal("1000000")  # ₹/quintal; anything above is a data error
ANOMALY_FACTOR = 3.0  # modal ≥3× or ≤⅓ of the recent median → accepted with warning
ANOMALY_WINDOW = 5  # recent reports used for the median
STALE_DAYS = 30  # a "current daily" dataset should not carry month-old reports

INDIAN_STATES = {
    "andaman and nicobar", "andaman and nicobar islands", "andhra pradesh", "arunachal pradesh", "assam", "bihar",
    "chandigarh", "chattisgarh", "chhattisgarh", "dadra and nagar haveli", "dadra and nagar haveli and daman and diu",
    "daman and diu", "delhi", "nct of delhi", "goa", "gujarat", "haryana", "himachal pradesh", "jammu and kashmir",
    "jharkhand", "karnataka", "kerala", "ladakh", "lakshadweep", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "puducherry", "pondicherry", "punjab", "rajasthan",
    "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttrakhand", "west bengal",
}

ALIASES: dict[str, tuple[str, ...]] = {
    "state": ("state", "state_name"),
    "district": ("district", "district_name"),
    "market": ("market", "market_name", "market_center", "apmc", "apmc_name", "mandi", "mandi_name"),
    "commodity": ("commodity", "commodity_name"),
    "variety": ("variety", "variety_name"),
    "grade": ("grade",),
    "arrival_date": ("arrival_date", "price_date", "reported_date", "date"),
    "min_price": ("min_price", "minimum_price", "min_price_rs_quintal", "min_price_rs"),
    "max_price": ("max_price", "maximum_price", "max_price_rs_quintal", "max_price_rs"),
    "modal_price": ("modal_price", "modal_price_rs_quintal", "modal_price_rs"),
    "unit": ("unit", "price_unit", "unit_of_price"),
}
REQUIRED = ("state", "market", "commodity", "arrival_date", "modal_price")
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d/%m/%y")

# Price unit → multiplier to ₹ per quintal.
UNITS = {
    "rs_quintal": 1, "quintal": 1, "inr_quintal": 1, "rs_qtl": 1, "qtl": 1, "per_quintal": 1,
    "rs_kg": 100, "kg": 100, "inr_kg": 100, "per_kg": 100,
    "rs_tonne": Decimal("0.1"), "tonne": Decimal("0.1"), "inr_tonne": Decimal("0.1"), "rs_ton": Decimal("0.1"),
}


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


def normalize_name(value) -> str:
    """Collapse whitespace; title-case names published in ALL CAPS or all lower case."""
    s = " ".join(str(value or "").split())
    if s and (s.isupper() or s.islower()):
        s = s.title()
    return s


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


def record_id(raw: dict) -> str:
    """Stable id for a source record that has none of its own (hash of its canonical JSON)."""
    canon = json.dumps({str(k): (None if v is None else str(v)) for k, v in raw.items()}, sort_keys=True)
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()[:32]


@dataclass
class RowResult:
    clean: dict | None
    issues: list[dict] = field(default_factory=list)


def _issue(row, field_, severity, code, message, raw):
    return {"row_number": row, "field": field_, "severity": severity, "code": code, "message": message, "raw": raw}


def validate_row(raw: dict, row_number: int, hmap: dict[str, str] | None = None, today: date | None = None,
                 stale_days: int | None = None) -> RowResult:
    today = today or today_ist()
    hmap = hmap if hmap is not None else header_map(raw.keys())
    data = {canon: raw.get(orig) for orig, canon in hmap.items()}
    issues: list[dict] = []
    raw_json = {str(k): (None if v is None else str(v)) for k, v in raw.items()}

    def err(f, code, msg):
        issues.append(_issue(row_number, f, IssueSeverity.ERROR, code, msg, raw_json))

    def warn(f, code, msg):
        issues.append(_issue(row_number, f, IssueSeverity.WARNING, code, msg, raw_json))

    text = {k: normalize_name(data.get(k)) for k in ("state", "district", "market", "commodity", "variety", "grade")}
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
        elif stale_days is not None and (today - arrival).days > stale_days:
            warn("arrival_date", "STALE_OBSERVATION",
                 f"Reported {arrival}, {(today - arrival).days} days ago, in a dataset expected to be current")

    factor = Decimal(1)
    unit_raw = data.get("unit")
    if unit_raw not in (None, ""):
        key = normalize_header(str(unit_raw).replace("/", " ").replace(".", ""))
        if key not in UNITS:
            err("unit", "INVALID_UNIT", f"Unknown price unit '{unit_raw}' (expected ₹/quintal, ₹/kg or ₹/tonne)")
        else:
            factor = Decimal(UNITS[key])
            if factor != 1:
                warn("unit", "CONVERTED_UNIT", f"Prices converted from '{unit_raw}' to ₹ per quintal")

    prices: dict[str, Decimal | None] = {}
    for f in ("min_price", "max_price", "modal_price"):
        try:
            p = parse_price(data.get(f))
        except ValueError as e:
            err(f, "NOT_A_NUMBER", str(e))
            prices[f] = None
            continue
        prices[f] = (p * factor).quantize(Decimal("0.01")) if p is not None else None
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

    if text["state"] and text["state"].lower() not in INDIAN_STATES:
        warn("state", "UNKNOWN_REGION", f"'{text['state']}' is not a recognised Indian state or union territory")

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
class Accepted:
    """A validated row plus its provenance."""

    row_number: int
    row: dict
    raw: dict
    source_record_id: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_in_batch: int = 0
    warnings: int = 0


def _recent_modals(db: Session, source_id, org_id, row) -> list[Decimal]:
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
        .limit(ANOMALY_WINDOW)
    )
    return list(db.scalars(stmt))


def upsert_prices(db: Session, run: IngestionRun, rows: list[Accepted], org_id, fetched_at: datetime, *,
                  dataset: str | None, endpoint: str | None) -> UpsertStats:
    """Insert new rows, update changed ones, count identical ones. Flags price anomalies."""
    stats = UpsertStats()
    keyed: dict[str, Accepted] = {}
    for a in rows:
        k = dedupe_key(run.source_id, org_id, a.row)
        if k in keyed:
            stats.duplicate_in_batch += 1  # last duplicate in a batch wins
        keyed[k] = a
    existing: dict[str, MarketPrice] = {}
    keys = list(keyed)
    for i in range(0, len(keys), 500):
        for mp in db.scalars(select(MarketPrice).where(MarketPrice.dedupe_key.in_(keys[i:i + 500]))):
            existing[mp.dedupe_key] = mp

    for key, a in keyed.items():
        row = a.row
        notes = list(a.warnings)
        recent = _recent_modals(db, run.source_id, org_id, row)
        if recent and row["modal_price"]:
            median = Decimal(str(statistics.median(recent)))
            ratio = float(row["modal_price"] / median) if median else 0
            if ratio >= ANOMALY_FACTOR or (ratio and ratio <= 1 / ANOMALY_FACTOR):
                desc = f"{ratio:.1f}× higher" if ratio >= 1 else f"{1 / ratio:.1f}× lower"
                msg = (f"Price anomaly: ₹{row['modal_price']}/quintal is {desc} than recent observations "
                       f"(median ₹{median} over {len(recent)} report{'s' if len(recent) != 1 else ''}). "
                       "Accepted with warning.")
                notes.append(msg)
                stats.warnings += 1
                db.add(IngestionIssue(run_id=run.id, row_number=a.row_number, field="modal_price",
                                      severity=IssueSeverity.WARNING, code="UNUSUAL_CHANGE", message=msg,
                                      raw={k: str(v) for k, v in row.items()}))
        prov = {
            "source_record_id": a.source_record_id, "source_dataset": dataset, "source_endpoint": endpoint,
            "raw_reference": a.raw, "validation_notes": notes or None,
            "validation_status": ValidationStatus.ACCEPTED_WITH_WARNING if notes else ValidationStatus.ACCEPTED,
        }
        values = {"min_price": row["min_price"], "max_price": row["max_price"], "modal_price": row["modal_price"]}
        mp = existing.get(key)
        if mp is None:
            db.add(MarketPrice(dedupe_key=key, organization_id=org_id, source_id=run.source_id, run_id=run.id,
                               fetched_at=fetched_at, **{k: row[k] for k in (
                                   "state", "district", "market", "commodity", "variety", "grade", "arrival_date")},
                               **values, **prov))
            stats.inserted += 1
        elif any(getattr(mp, k) != v for k, v in values.items()):
            for k, v in {**values, **prov}.items():
                setattr(mp, k, v)
            mp.run_id, mp.fetched_at = run.id, fetched_at
            stats.updated += 1
        else:
            # Same observation re-published: keep the original run as its provenance, record the re-confirmation.
            mp.fetched_at = fetched_at
            stats.unchanged += 1
    return stats


def record_issues(db: Session, run: IngestionRun, issues: list[dict]) -> None:
    for i in issues:
        db.add(IngestionIssue(run_id=run.id, **i))


def warnings_for(issues: list[dict], row_number: int) -> list[str]:
    return [i["message"] for i in issues if i["row_number"] == row_number and i["severity"] == IssueSeverity.WARNING]
