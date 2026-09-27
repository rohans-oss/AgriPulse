# AgriFlow AI — AgriPulse

Agricultural supply-chain intelligence platform for India, built version by version.

**Current version: V2 — Data Platform** (on top of V1 — Core Platform).

- **V1:** authentication, organizations, roles and permissions, location scope, regions,
  commodities, warehouses, inventory and a dashboard specific to each role.
- **V2:** real public data (AGMARKNET mandi prices via data.gov.in, Open-Meteo weather),
  CSV import (market price history and bulk inventory) with dry-run validation, data-quality
  checks, ingestion history, honest freshness labels, and a full UI redesign.

Forecasting, price models, spoilage risk, the knowledge graph, optimization, what-if simulation
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
    ingest.py           CLI for scheduled ingestion
  alembic/              migrations
  tests/                API tests
frontend/
  src/app/(auth)        login, register
  src/app/(app)         dashboard, inventory, warehouses, commodities, regions, users, settings
  src/components        app shell, tables, modals, charts
  src/lib               API client, auth context, types
```

## Run locally

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

**Scheduling.** Run the CLI from cron / Task Scheduler, e.g. weather hourly and prices each evening:

```bash
0 * * * *   cd backend && python -m app.ingest weather --org agriflow-demo-foods
30 19 * * * cd backend && python -m app.ingest market  --org agriflow-demo-foods
```

**Data quality.** Every row passes the same checks whether it comes from an API or a CSV:
required fields, parseable dates, no future dates, positive and plausible prices, min ≤ max
(rejected), modal outside min–max and >3× jumps vs the previous report (kept, flagged), and
plausible weather ranges. Rejected rows are never stored; every issue is visible on the run page.
Re-fetching is idempotent (rows are de-duplicated and updated in place).

**Visibility.** Official public rows are shared across organizations; uploads, weather and
ingestion runs are private to the organization, and weather follows location scope.

## Tests

```bash
cd backend
pytest                                                         # SQLite in memory (54 tests)
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

V1 core platform ✓ · V2 data platform ✓ · V3 demand intelligence · V4 price intelligence · V5 spoilage & risk ·
V6 knowledge graph · V7 optimization · V8 what-if simulation · V9 AI operations assistant ·
V10 production platform.
