# V3 data-provenance audit

Audit of AgriPulse at the end of V2 (commit `45fc809`), done before V3 changes.
Every dataset the UI displays is classified as one of:

| Class | Meaning |
|---|---|
| `REAL_EXTERNAL` | Fetched from a verified public source (government / documented public API) |
| `REAL_ORGANIZATION` | Provided by the organization: manual entry, CSV import, future API/ERP |
| `SYNTHETIC_DEMO` | Invented by the seed script for demos and tests |
| `MODEL_PREDICTION` | Produced by a model (external provider forecast now; our own models from V4) |
| `UNAVAILABLE` | No verified data exists |

## Findings (V2)

| Where shown | Dataset | V2 origin | V2 class | Problem found | V3 fix |
|---|---|---|---|---|---|
| Dashboard KPIs, inventory/warehouse/stock tables, inventory by commodity/region, capacity bars | `inventory_items`, `warehouses.capacity_tonnes` | Seed script (demo org) or manual entry | SYNTHETIC_DEMO **or** REAL_ORGANIZATION | Labelled only per *organization* (`is_demo`). A real CSV import into the demo org would still say "synthetic"; synthetic rows edited with real counts were indistinguishable. | Per-record `data_origin` on inventory, movements and warehouses; aggregates report their origin mix |
| Movement history, inbound/outbound totals, daily movement chart | `inventory_movements` | Seed script back-dates 14 days of invented movements | SYNTHETIC_DEMO | Same per-org labelling; back-dated synthetic timestamps looked like real history | Per-record `data_origin`; synthetic rows labelled on every table row |
| Market price cards, trend chart, reports table | `market_prices` (data.gov.in) | AGMARKNET via data.gov.in | REAL_EXTERNAL | Old data kept its "Daily" label after a failed fetch; no per-row provenance (endpoint, dataset, raw record) | `ERROR` freshness, provenance columns, provenance view |
| Same, uploaded files | `market_prices` (CSV) | Organization upload | REAL_ORGANIZATION | OK (labelled "Uploaded file · Historical") | Class made explicit |
| Weather cards, rainfall / temperature charts | `weather_observations` | Open-Meteo | REAL_EXTERNAL (model estimate) | Reading stayed "Current" after a failed refresh; no forecast separation | `ERROR`/stale handling; forecasts stored separately as MODEL_PREDICTION |
| Data sources page | `data_sources`, `ingestion_runs` | System | — | No endpoint/auth status/last failure; manual-only refresh | Source health model + scheduler |
| Demand history | — | Not built | UNAVAILABLE | Not shown | Shown explicitly as "No verified historical data" in the data environment panel |
| Predictions | — | None exist | — | — | Nothing is labelled as a prediction except provider forecasts |

## Hard-coded / random values scan

- Backend: `random` is used only in `app/seed.py` (demo movement history). No API returns generated values.
- Frontend: no hard-coded metrics, chart arrays or timestamps. The only literals are the demo account list on the login page (credentials, not data).
- Tests: `tests/fixtures/open_meteo_*.json` are **real** responses recorded from api.open-meteo.com via the user's browser;
  `tests/fixtures/ogd_mandi_synthetic.json` is **synthetic**, labelled in-file, used only by tests.

## Reachability (from the build sandbox, 27 Sep 2026)

| Source | Reachable from sandbox | Reachable from user's PC | Verified |
|---|---|---|---|
| api.open-meteo.com | No (egress allowlist) | Yes | Real responses recorded via the user's browser |
| api.data.gov.in | No | Yes (endpoint answers "Authorization field missing" without key) | Needs the user's API key — not entered by the assistant |
| IMD API | No | Requires IP whitelisting | Not integrated |
