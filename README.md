# AgriFlow AI — AgriPulse

Agricultural supply-chain intelligence platform for India, built version by version.

**Current version: V3 — Real-data enforcement & first intelligence layer** (on top of V1 and V2).

- **V1:** authentication, organizations, roles and permissions, location scope, regions,
  commodities, warehouses, inventory and a dashboard specific to each role.
- **V2:** real public data (AGMARKNET mandi prices via data.gov.in, Open-Meteo weather),
  CSV import (market price history and bulk inventory) with dry-run validation, data-quality
  checks, ingestion history, honest freshness labels, and a full UI redesign.
- **V3:** every figure carries its data class (real external / organization / synthetic demo /
  forecast / unavailable) and provenance down to the ingestion run; source health (status, auth,
  endpoint, rows, last failure, next fetch); an automatic ingestion scheduler; ERROR freshness
  when a refresh fails; a *Data environment* panel on every dashboard; market comparisons by
  market/district/state; weather forecasts (labelled as model predictions) and rule-based
  disruption indicators; server-side filters; and a one-command Windows launcher.

No AgriFlow ML model exists yet — nothing on screen is an AgriFlow prediction. Forecasting, price models, spoilage risk, the knowledge graph, optimization, what-if simulation
and the AI assistant are later versions (V3–V9) and are **not** in this codebase yet.

> **Two kinds of data, never mixed.** The demo workspace's organization figures (stock, capacity,
> movements) are **synthetic** and labelled so on every page. Market prices and weather are
> **real public data** from the sources below, each shown with its source and timestamps.
> Nothing is labelled "live": weather is *current* (with its reading time), mandi prices are
> *daily*, uploads are *historical*, and missing data is shown as *unavailable* — never estimated.

## Stack

| Layer    | Tech |
|----------|------|
| Backend  | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, PyJWT, bcrypt |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4 |
| Tests    | pytest (Postgres or SQLite), Playwright used for end-to-end verification |

```
backend/
  app/
    api/deps.py         AuthContext: user → org → roles → permissions → location scope
    api/routes/         auth, organization, users, regions, commodities, warehouses, inventory,
                        dashboard, data (sources, runs, market, weather, imports)
    models/             SQLAlchemy models + enums
    schemas/            Pydantic request/response schemas
    services/rbac.py    permission & role catalog (single source of truth)
    services/data/      V2: source catalog, connectors, validation, freshness, imports, queries
    seed.py             synthetic demo workspace
    ingest.py           CLI: fetch now (weather | market | all)
    scheduler.py        V3 automatic-refresh worker
  alembic/              migrations
  tests/                API tests
frontend/
  src/app/(auth)        login, register
  src/app/(app)         dashboard, inventory, warehouses, commodities, regions, users, settings
  src/components        app shell, tables, modals, charts
  src/lib               API client, auth context, types
```

## Run on Windows (one command)

```powershell
git clone https://github.com/rohans-oss/AgriPulse.git
cd AgriPulse
.\run-local.bat            # or: powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```

Needs Python 3.11+ and Node 20+ — no Docker or PostgreSQL. It creates `backend\.env` (SQLite,
random JWT secret), migrates, seeds the synthetic demo workspace (`-NoDemo` to skip, `-Reset` to
start over), builds the web app, and opens three windows: API, scheduler, web. Sign in at
http://localhost:3000.

For real mandi prices, add your free data.gov.in key to `backend\.env` yourself
(`DATA_GOV_IN_API_KEY=...`) and re-run. The key stays server-side; the browser never receives it.

## Run locally (PostgreSQL)

Prerequisites: Python 3.11+, Node 20+, PostgreSQL 16 (or Docker for the database only).

**1. Database**

```bash
docker compose up -d db          # or use a local Postgres:
# createuser -P agriflow   (password: agriflow)
# createdb -O agriflow agriflow && createdb -O agriflow agriflow_test
```

**2. Backend** (terminal 1)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # set JWT_SECRET
alembic upgrade head                                   # create schema
python -m app.seed                                     # optional synthetic demo org
uvicorn app.main:app --reload --port 8000              # API docs: http://localhost:8000/docs
```

**3. Frontend** (terminal 2)

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                                            # http://localhost:3000
```

Register a new workspace, or sign in with a demo account (password `Demo@1234`):

| Account | Role | Scope |
|---|---|---|
| admin@agriflow.demo | Organization Admin | all locations |
| ops@agriflow.demo | Operations Manager | all locations |
| procurement@agriflow.demo | Procurement Manager | all locations |
| ravi@agriflow.demo | Warehouse Manager | Bengaluru Central Warehouse only |
| logistics@agriflow.demo | Logistics Manager | all locations |
| analyst@agriflow.demo | Analyst | all locations |
| viewer@agriflow.demo | Viewer | Mysuru region only |

`python -m app.seed --reset` rebuilds the demo org.

## External data (V2)

| Source | What | Origin | Updates | Setup |
|---|---|---|---|---|
| AGMARKNET daily mandi prices (data.gov.in, resource `9ef84268-…`) | Min / max / modal price, ₹ per quintal, per market & commodity | Official government | Daily | Free API key → `DATA_GOV_IN_API_KEY` |
| Open-Meteo | Current conditions + completed-day rainfall/temperature at each warehouse's coordinates | Documented public API (model-based, not IMD stations) | Current every 15 min; daily after the day ends | None — add latitude/longitude to warehouses |
| Uploaded market price files | Historical price files, e.g. AGMARKNET exports | Your organization (private) | On upload | Import CSV page |
| Uploaded inventory files | Bulk stock updates | Your organization | On upload | Import CSV page |

**Get real data flowing**

1. Add coordinates to your warehouses (demo warehouses already have them).
2. *Data sources → Open-Meteo → Fetch now* (or `python -m app.ingest weather --org <workspace-id>`).
3. Get a free key at [data.gov.in](https://data.gov.in) (sign in → My Account → API key), put it in
   `backend/.env` as `DATA_GOV_IN_API_KEY=...`, restart the API, then *Fetch now* on the mandi source.
   `MANDI_STATES` controls which states are fetched (default Karnataka).
4. If a commodity's AGMARKNET name differs from yours (e.g. Rice → `Paddy(Dhan)(Common)`), set
   *Name in market data* on the commodity.

**Automatic refresh (V3).** Run the scheduler next to the API:

```bash
cd backend
python -m app.scheduler            # checks every 60 s, runs whatever is due
python -m app.scheduler --once     # a single tick, for cron / Windows Task Scheduler
```

What is due is computed from the ingestion history in the database, so restarts never
double-fetch. Weather is fetched per organization every `WEATHER_REFRESH_MINUTES` (default 60;
Open-Meteo updates current conditions every 15 min). Mandi prices are one shared public fetch at
`MARKET_FETCH_TIMES_IST` (default 10:30, 14:30, 19:30 IST) — data.gov.in is a daily dataset, so
polling more often only wastes the rate limit. After a failure it retries after
`RETRY_AFTER_FAILURE_MINUTES` (default 20). Each organization can switch auto-refresh off per
source on the Data sources page. The worker writes a heartbeat; the UI says so when it is not running.

To fetch immediately from the command line: `python -m app.ingest weather|market|all [--org slug]`.

**Data quality.** Every row passes the same checks whether it comes from an API or a CSV:
required fields, parseable dates, no future dates, positive and plausible prices, min ≤ max
(rejected), modal outside min–max and >3× jumps vs the previous report (kept, flagged), and
plausible weather ranges. Rejected rows are never stored; every issue is visible on the run page.
Re-fetching is idempotent (rows are de-duplicated and updated in place).

**Visibility.** Official public rows and their (public) fetch runs are shared across
organizations — another workspace's name is never shown on them. Uploads, weather, organization
runs and source settings are private to the organization, and weather follows location scope.

## Real data rules (V3)

| Data class | Meaning | Where |
|---|---|---|
| `REAL_EXTERNAL` | Fetched from a named public source | Mandi prices (AGMARKNET), weather (Open-Meteo) |
| `REAL_ORGANIZATION` | Entered manually or imported by the organization | Inventory, warehouses, uploaded price files |
| `SYNTHETIC_DEMO` | Created by the demo seed | Demo workspace inventory, warehouses, movements |
| `MIXED` | A section containing both of the above | Demo workspace after someone edits a record |
| `MODEL_PREDICTION` | A model output, never an observation | Only Open-Meteo's own forecast (labelled "Forecast") |
| `UNAVAILABLE` | No verified data | Shown as "No verified … available", never filled in |

Every inventory item, movement and warehouse has a `data_origin` (`SYNTHETIC_DEMO`,
`MANUAL_ENTRY`, `CSV_IMPORT`, `API`); editing a synthetic record makes it organization data.

**Freshness:** `CURRENT` (weather reading ≤ 90 min old), `RECENT` (≤ 24 h), `DAILY` (mandi report
from today/yesterday), `HISTORICAL` (older, or an uploaded file), `UNAVAILABLE` (no verified data),
`ERROR` (verified data exists but the latest refresh failed — the card says when the data was last
verified and why the refresh failed). Nothing is ever labelled "live".

**Provenance:** each stored price keeps `source_record_id`, `source_dataset`, `source_endpoint`
(never the API key), `raw_reference` (the record as received), `fetched_at`, the ingestion run and
its validation status/notes. *Market prices → Source* opens this for any row. Weather readings
keep the same fields.

**Weather indicators** are published thresholds, not ML: IMD 24-hour rainfall categories
(moderate ≥ 15.6 mm, heavy ≥ 64.5 mm), heat ≥ 35 °C / 40 °C, gusts ≥ 40 / 60 km/h, thunderstorm
weather codes, warm-and-humid storage conditions. Each one states its rule and whether it used an
observation or the provider's forecast. Readings older than 6 h are not evaluated.

**Source health** (Data sources page and `GET /api/data/sources`): status (`CONNECTED`,
`DEGRADED`, `FAILING`, `NOT_CONFIGURED`, `NOT_CONNECTED`, …), auth status, endpoint, expected
refresh, last fetch started/completed, last success, last failure with its kind (`TIMEOUT`,
`NETWORK`, `AUTH`, `RATE_LIMITED`, `HTTP`, `MALFORMED`), rows received/accepted/unchanged/rejected,
next scheduled fetch and scheduler heartbeat.

**New endpoints:** `GET /api/data/environment`, `GET|PATCH /api/data/sources/{key}/settings`,
`GET /api/market/prices/{id}` (provenance), `GET /api/market/compare?commodity=&by=market|district|state&days=`,
filters `validation` and `freshness` on `/api/market/prices`, `region_id`/`warehouse_id` on
`/api/weather/current`, `region_id` on `/api/dashboard`. The full audit of every dataset is in
[`docs/V3_DATA_AUDIT.md`](docs/V3_DATA_AUDIT.md).

## Tests

```bash
cd backend
pytest                                                         # SQLite in memory (74 tests)
TEST_DATABASE_URL=postgresql+psycopg://agriflow:agriflow@localhost:5432/agriflow_test pytest
```

## How access control works

Every API request is resolved server-side into an `AuthContext`:

```
session token → auth_sessions row (not revoked/expired) → user (active)
  → organization → roles → permissions → location scope → allowed warehouse ids
```

- **Authentication.** bcrypt password hashes; login creates an `auth_sessions` row and issues a
  JWT (HS256) carrying the user id and session id. The browser gets it as an `httpOnly`,
  `SameSite=Lax` cookie through the same-origin `/api` proxy; API clients can send it as
  `Authorization: Bearer`. Logout, deactivation and password resets revoke sessions server-side.
- **Permissions.** Endpoints declare what they need, e.g. `Depends(require(P.INVENTORY_UPDATE))`.
  Roles map to permissions in `services/rbac.py`, which is synced into the `roles`,
  `permissions` and `role_permissions` tables on startup. Hiding buttons in the UI is cosmetic;
  the backend refuses the request regardless.
- **Organization isolation.** The organization comes only from the session, never from the
  request. Every query filters on `organization_id`; rows from other organizations return
  **404** so their existence is not revealed. IDs in request bodies (region, warehouse,
  commodity, scope) are checked against the caller's organization.
- **Location scope.** Admins see everything. Other users see only warehouses in regions or
  individual warehouses granted in `user_location_scopes`, or all locations when
  `org_wide_access` is set. It **fails closed**: a user with no scope sees no warehouses.
  Out-of-scope warehouses in the same organization return **403**. Scope applies to warehouse
  lists, inventory, movements and dashboard figures.
- **Audit.** Logins, failed logins, logouts, and create/update/delete of users, regions,
  commodities, warehouses and inventory are written to `audit_logs` in the same transaction as
  the change. Admins can view them under Settings.

## Roles (V1)

| Permission | Admin | Ops | Procurement | Warehouse | Logistics | Analyst | Viewer |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| region / commodity / warehouse / inventory `.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| inventory `.create` `.update` `.delete` | ✓ | ✓ | | ✓ | | | |
| region / commodity / warehouse `.manage` | ✓ | | | | | | |
| procurement.read | ✓ | ✓ | ✓ | | | | |
| procurement.create *(reserved for a later version)* | ✓ | | ✓ | | | | |
| logistics.read | ✓ | ✓ | | | ✓ | | |
| analytics.read | ✓ | ✓ | | | | ✓ | |
| users.read, users.manage, settings.manage, audit.read | ✓ | | | | | | |
| data.read (market, weather, sources) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| data.ingest (fetch from external sources) | ✓ | ✓ | | | | | |
| data.import (upload market price files) | ✓ | ✓ | | | | ✓ | |

## Design

Warm neutral surfaces, a forest-green brand with a harvest-gold accent, Inter for UI text and
Fraunces for a few display headings (both self-hosted via `@fontsource`, no external font
requests). The farmland illustration (`frontend/public/art/fields.svg`) is original artwork
generated by `frontend/scripts/generate-art.mjs`. Motion is CSS-only (entrance fades, count-up
numbers, chart draw-in, skeletons) and is disabled under `prefers-reduced-motion`.

## Roadmap

V1 core platform ✓ · V2 data platform ✓ · V3 real-data enforcement ✓ · V4 demand & price intelligence · V5 spoilage & risk ·
V6 knowledge graph · V7 optimization · V8 what-if simulation · V9 AI operations assistant ·
V10 production platform.
