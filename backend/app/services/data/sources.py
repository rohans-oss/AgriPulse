"""Catalog of data sources. Synced into ``data_sources`` on startup, like the RBAC catalog."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataSource
from app.models.enums import DataKind, SourceOrigin

OGD_MANDI = "ogd_mandi_prices"
OPEN_METEO = "open_meteo_weather"
CSV_MARKET = "csv_market_prices"
CSV_INVENTORY = "csv_inventory"

SOURCES: dict[str, dict] = {
    OGD_MANDI: {
        "name": "AGMARKNET daily mandi prices (data.gov.in)",
        "publisher": "Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare "
        "— via Open Government Data Platform India (data.gov.in)",
        "kind": DataKind.MARKET_PRICES,
        "origin": SourceOrigin.OFFICIAL_API,
        "homepage_url": "https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi",
        "license": "Government Open Data License – India",
        "update_frequency": "Daily — each mandi reports prices for the day's arrivals",
        "description": "Minimum, maximum and modal (most common) wholesale prices in ₹ per quintal, as reported "
        "by APMC mandis to AGMARKNET. The dataset holds the latest reported day; history builds up "
        "as it is fetched each day. Requires a free data.gov.in API key.",
    },
    OPEN_METEO: {
        "name": "Open-Meteo weather at warehouse locations",
        "publisher": "Open-Meteo.com — forecast and analysis models from national weather services "
        "(ECMWF, NOAA, DWD and others)",
        "kind": DataKind.WEATHER,
        "origin": SourceOrigin.PUBLIC_API,
        "homepage_url": "https://open-meteo.com/en/docs",
        "license": "CC BY 4.0",
        "update_frequency": "Current conditions every 15 minutes; daily totals once the day has ended",
        "description": "Model-based estimates for each warehouse's coordinates (temperature, humidity, rainfall, "
        "wind). These are not IMD station observations; IMD's API requires IP whitelisting and is "
        "planned as an additional source.",
    },
    CSV_MARKET: {
        "name": "Uploaded market price files",
        "publisher": "Your organization (CSV upload)",
        "kind": DataKind.MARKET_PRICES,
        "origin": SourceOrigin.USER_UPLOAD,
        "homepage_url": "https://agmarknet.gov.in/",
        "license": "As provided by the uploader",
        "update_frequency": "When a file is uploaded",
        "description": "Historical price files uploaded by your team, e.g. AGMARKNET report exports. Visible only "
        "to your organization and always labelled with the file name and uploader.",
    },
    CSV_INVENTORY: {
        "name": "Uploaded inventory files",
        "publisher": "Your organization (CSV upload)",
        "kind": DataKind.INVENTORY,
        "origin": SourceOrigin.USER_UPLOAD,
        "homepage_url": "",
        "license": "Organization data",
        "update_frequency": "When a file is uploaded",
        "description": "Bulk stock updates for your warehouses. Every change is recorded as an inventory movement.",
    },
}

# Sources a user can trigger from the app (the rest are uploads).
FETCHABLE = {OGD_MANDI, OPEN_METEO}


def sync_sources(db: Session) -> None:
    existing = {s.key: s for s in db.scalars(select(DataSource))}
    for key, spec in SOURCES.items():
        src = existing.get(key) or DataSource(key=key)
        for field, value in spec.items():
            setattr(src, field, value)
        db.add(src)
    db.commit()


def get_source(db: Session, key: str) -> DataSource:
    src = db.scalar(select(DataSource).where(DataSource.key == key))
    if src is None:  # pragma: no cover - synced on startup
        raise LookupError(f"Unknown data source {key}")
    return src
