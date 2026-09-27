"""CSV imports: market price history files and bulk inventory updates.

Both follow the same flow: parse → validate every row → (dry run) report, or (commit) apply.
Market price rows that fail validation are skipped and recorded as issues; an inventory file is
applied only if every row is valid, because it changes the organization's own stock figures.
"""

import csv
import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import Commodity, IngestionRun, InventoryItem, InventoryMovement, Warehouse
from app.models.enums import DataOrigin, IssueSeverity, MovementType, RecordStatus, RunStatus, RunTrigger, WarehouseStatus
from app.schemas.data import ImportResult, IssueOut
from app.services.audit import record_audit
from app.services.data import market
from app.services.data.sources import CSV_INVENTORY, CSV_MARKET, get_source
from app.services.serializers import to_tonnes, warehouse_usage

MAX_ROWS = 50_000
ISSUE_LIMIT = 200


def read_csv(content: bytes, max_bytes: int) -> tuple[list[str], list[dict]]:
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {max_bytes // 1_000_000} MB")
    if not content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Could not find a header row")
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"More than {MAX_ROWS:,} rows; split the file")
        if any((v or "").strip() for k, v in row.items() if k is not None):
            rows.append({k: v for k, v in row.items() if k is not None})
    return [h for h in reader.fieldnames if h], rows


def _issues_out(issues: list[dict]) -> list[IssueOut]:
    return [IssueOut(row_number=i["row_number"], field=i["field"], severity=str(i["severity"].value
                     if hasattr(i["severity"], "value") else i["severity"]), code=i["code"],
                     message=i["message"], raw=i["raw"]) for i in issues[:ISSUE_LIMIT]]


def _jsonable(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if isinstance(v, Decimal) else v))
            for k, v in row.items()}


# --------------------------------------------------------------------------- market prices


def import_market_prices(db: Session, ctx: AuthContext, file_name: str, content: bytes, dry_run: bool,
                         max_bytes: int, request: Request) -> ImportResult:
    headers, rows = read_csv(content, max_bytes)
    hmap = market.header_map(headers)
    detected = {orig: canon for orig, canon in hmap.items()}
    missing = [f for f in market.REQUIRED if f not in hmap.values()]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Missing required column(s): {', '.join(missing)}. "
                            "Expected headers like State, District, Market, Commodity, Variety, Grade, "
                            "Arrival_Date, Min_Price, Max_Price, Modal_Price.")
    accepted: list[market.Accepted] = []
    issues: list[dict] = []
    for n, raw in enumerate(rows, start=2):  # row 1 is the header
        res = market.validate_row(raw, n, hmap)
        issues += res.issues
        if res.clean:
            accepted.append(market.Accepted(n, res.clean, dict(raw), f"{file_name}#row{n}",
                                            market.warnings_for(res.issues, n)))
    rejected = sum(1 for i in issues if i["severity"] == IssueSeverity.ERROR)
    warnings = sum(1 for i in issues if i["severity"] == IssueSeverity.WARNING)
    result = ImportResult(dry_run=dry_run, run_id=None, file_name=file_name, columns_detected=detected,
                          missing_columns=[], rows_total=len(rows), rows_valid=len(accepted),
                          rows_rejected=rejected, warnings=warnings, issues=_issues_out(issues),
                          preview=[_jsonable(a.row) for a in accepted[:20]])
    if dry_run:
        return result
    if not accepted:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No valid rows to import")

    src = get_source(db, CSV_MARKET)
    run = IngestionRun(source_id=src.id, organization_id=ctx.org_id, triggered_by_id=ctx.user.id,
                       trigger=RunTrigger.UPLOAD, file_name=file_name, rows_received=len(rows),
                       params={"columns": detected}, endpoint="upload")
    db.add(run)
    db.flush()
    market.record_issues(db, run, issues)
    stats = market.upsert_prices(db, run, accepted, ctx.org_id, datetime.now(UTC),
                                 dataset=f"Upload: {file_name}", endpoint="upload")
    run.rows_inserted, run.rows_updated, run.rows_unchanged = stats.inserted, stats.updated, stats.unchanged
    run.rows_duplicate = stats.unchanged + stats.duplicate_in_batch
    run.rows_rejected, run.warnings = rejected, warnings + stats.warnings
    run.status = RunStatus.PARTIAL if rejected else RunStatus.SUCCESS
    run.finished_at = datetime.now(UTC)
    record_audit(db, action="data.import", entity_type="ingestion_run", entity_id=run.id, organization_id=ctx.org_id,
                 actor_user_id=ctx.user.id, request=request,
                 details={"source": CSV_MARKET, "file": file_name, "inserted": stats.inserted,
                          "updated": stats.updated, "rejected": rejected})
    db.commit()
    result.run_id = run.id
    result.inserted, result.updated, result.unchanged = stats.inserted, stats.updated, stats.unchanged
    result.warnings = run.warnings
    return result


# --------------------------------------------------------------------------- inventory

INV_ALIASES = {
    "warehouse": ("warehouse", "warehouse_name"),
    "commodity": ("commodity", "commodity_name", "product"),
    "quantity": ("quantity", "qty", "stock", "quantity_on_hand"),
    "notes": ("notes", "note", "remarks"),
}


def _inv_map(headers) -> dict[str, str]:
    lookup = {a: c for c, aliases in INV_ALIASES.items() for a in aliases}
    out = {}
    for h in headers:
        canon = lookup.get(market.normalize_header(h))
        if canon and canon not in out.values():
            out[h] = canon
    return out


def import_inventory(db: Session, ctx: AuthContext, file_name: str, content: bytes, dry_run: bool,
                     max_bytes: int, request: Request) -> ImportResult:
    headers, rows = read_csv(content, max_bytes)
    hmap = _inv_map(headers)
    missing = [f for f in ("warehouse", "commodity", "quantity") if f not in hmap.values()]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Missing required column(s): {', '.join(missing)}. Expected: warehouse, commodity, "
                            "quantity, notes (optional). Quantity is in the commodity's own unit.")
    warehouses = {w.name.strip().lower(): w for w in db.scalars(
        select(Warehouse).where(Warehouse.organization_id == ctx.org_id)).unique()}
    commodities = {c.name.strip().lower(): c for c in db.scalars(
        select(Commodity).where(Commodity.organization_id == ctx.org_id))}
    existing = {(i.warehouse_id, i.commodity_id): i for i in db.scalars(
        select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id)).unique()}

    issues: list[dict] = []
    planned: dict[tuple, dict] = {}
    for n, raw in enumerate(rows, start=2):
        data = {canon: (raw.get(orig) or "").strip() for orig, canon in hmap.items()}
        raw_json = {k: v for k, v in raw.items()}
        row_errors = []

        def err(field, code, msg, _row_errors=row_errors, _n=n, _raw=raw_json):
            _row_errors.append({"row_number": _n, "field": field, "severity": IssueSeverity.ERROR,
                                "code": code, "message": msg, "raw": _raw})

        wh = warehouses.get(data.get("warehouse", "").lower())
        com = commodities.get(data.get("commodity", "").lower())
        if not data.get("warehouse"):
            err("warehouse", "MISSING", "Warehouse is required")
        elif wh is None:
            err("warehouse", "UNKNOWN", f"No warehouse named '{data['warehouse']}' in your organization")
        elif not ctx.can_access_warehouse(wh.id):
            err("warehouse", "OUT_OF_SCOPE", f"'{wh.name}' is outside your location scope")
        elif wh.status != WarehouseStatus.ACTIVE:
            err("warehouse", "INACTIVE", f"'{wh.name}' is {wh.status.value}")
        if not data.get("commodity"):
            err("commodity", "MISSING", "Commodity is required")
        elif com is None:
            err("commodity", "UNKNOWN", f"No commodity named '{data['commodity']}' in your organization")
        elif com.status != RecordStatus.ACTIVE:
            err("commodity", "INACTIVE", f"'{com.name}' is inactive")
        qty = None
        try:
            qty = Decimal(re.sub(r"[,\s]", "", data.get("quantity", "")))
            if qty < 0:
                err("quantity", "NEGATIVE", "Quantity cannot be negative")
            elif qty != qty.quantize(Decimal("0.001")):
                err("quantity", "PRECISION", "Use at most 3 decimal places")
        except InvalidOperation:
            err("quantity", "NOT_A_NUMBER", f"'{data.get('quantity')}' is not a number")
        if wh and com and (wh.id, com.id) in planned:
            err("commodity", "DUPLICATE", f"{com.name} in {wh.name} appears more than once in this file")
        issues += row_errors
        if not row_errors:
            planned[(wh.id, com.id)] = {"row": n, "warehouse": wh, "commodity": com, "quantity": qty,
                                        "notes": data.get("notes", "")}

    # Capacity check with the file applied.
    usage = warehouse_usage(db, ctx.org_id, list({k[0] for k in planned}))
    delta_by_wh: dict = {}
    for (wid, cid), p in planned.items():
        cur = existing.get((wid, cid))
        before = to_tonnes(cur.quantity, p["commodity"].unit) if cur else 0.0
        delta_by_wh[wid] = delta_by_wh.get(wid, 0.0) + to_tonnes(p["quantity"], p["commodity"].unit) - before
    for wid, delta in delta_by_wh.items():
        wh = next(p["warehouse"] for p in planned.values() if p["warehouse"].id == wid)
        total = usage.get(wid, 0.0) + delta
        if total > float(wh.capacity_tonnes) + 1e-9:
            issues.append({"row_number": None, "field": "quantity", "severity": IssueSeverity.ERROR,
                           "code": "OVER_CAPACITY",
                           "message": f"{wh.name} would hold {total:,.3f} t, above its {float(wh.capacity_tonnes):,.3f} t capacity",
                           "raw": {}})

    errors = sum(1 for i in issues if i["severity"] == IssueSeverity.ERROR)
    preview = []
    for p in list(planned.values())[:20]:
        cur = existing.get((p["warehouse"].id, p["commodity"].id))
        preview.append({"row": p["row"], "warehouse": p["warehouse"].name, "commodity": p["commodity"].name,
                        "unit": p["commodity"].unit.value, "current": float(cur.quantity) if cur else None,
                        "new": float(p["quantity"]),
                        "action": "create" if cur is None else ("unchanged" if cur.quantity == p["quantity"] else "update")})
    result = ImportResult(dry_run=dry_run, run_id=None, file_name=file_name, columns_detected=hmap, missing_columns=[],
                          rows_total=len(rows), rows_valid=len(planned) if not errors else 0,
                          rows_rejected=len({i["row_number"] for i in issues if i["severity"] == IssueSeverity.ERROR}),
                          warnings=0, issues=_issues_out(issues), preview=preview)
    if dry_run:
        return result
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"The file has {errors} error(s). Fix them and upload again — nothing was changed.")
    if not planned:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No rows to import")

    src = get_source(db, CSV_INVENTORY)
    run = IngestionRun(source_id=src.id, organization_id=ctx.org_id, triggered_by_id=ctx.user.id,
                       trigger=RunTrigger.UPLOAD, file_name=file_name, rows_received=len(rows), params={})
    db.add(run)
    db.flush()
    reason = f"CSV import: {file_name}"[:255]
    for (wid, cid), p in planned.items():
        item = existing.get((wid, cid))
        if item is None:
            item = InventoryItem(organization_id=ctx.org_id, warehouse_id=wid, commodity_id=cid,
                                 quantity=p["quantity"], notes=p["notes"], updated_by_id=ctx.user.id,
                                 data_origin=DataOrigin.CSV_IMPORT)
            db.add(item)
            db.flush()
            kind, delta = MovementType.INITIAL, p["quantity"]
            run.rows_inserted += 1
        elif item.quantity == p["quantity"] and (not p["notes"] or p["notes"] == item.notes):
            run.rows_unchanged += 1
            continue
        else:
            delta = p["quantity"] - item.quantity
            item.quantity = p["quantity"]
            if p["notes"]:
                item.notes = p["notes"]
            item.updated_by_id = ctx.user.id
            item.data_origin = DataOrigin.CSV_IMPORT
            run.rows_updated += 1
            if delta == 0:
                continue
            kind = MovementType.INBOUND if delta > 0 else MovementType.OUTBOUND
        db.add(InventoryMovement(organization_id=ctx.org_id, inventory_item_id=item.id, warehouse_id=wid,
                                 commodity_id=cid, movement_type=kind, quantity_delta=delta,
                                 quantity_after=p["quantity"], reason=reason, created_by_id=ctx.user.id,
                                 data_origin=DataOrigin.CSV_IMPORT))
    run.status, run.finished_at = RunStatus.SUCCESS, datetime.now(UTC)
    record_audit(db, action="inventory.import", entity_type="ingestion_run", entity_id=run.id,
                 organization_id=ctx.org_id, actor_user_id=ctx.user.id, request=request,
                 details={"file": file_name, "created": run.rows_inserted, "updated": run.rows_updated,
                          "unchanged": run.rows_unchanged})
    db.commit()
    result.run_id = run.id
    result.inserted, result.updated, result.unchanged = run.rows_inserted, run.rows_updated, run.rows_unchanged
    return result

