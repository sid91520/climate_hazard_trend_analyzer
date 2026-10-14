# Climate Hazard Trend Analyzer: Heatwaves

Pick a place and a range of years. The app shows how **heatwave frequency, duration and
intensity** have changed there, with charts, trend statistics and an honest plain-English summary.

- **Live app:** _add your Vercel URL here_
- **API docs (Swagger):** _add your Render URL here_ `/docs`

Heatwave is the only hazard implemented. The code is laid out so drought or heavy rain could be
added as sibling modules (see [Extending to other hazards](#extending-to-other-hazards)).

---

## Contents

1. [Architecture](#architecture)
2. [Running locally](#running-locally)
3. [Deploying](#deploying)
4. [API](#api)
5. [Data source and its limitations](#data-source-and-its-limitations)
6. [Hazard logic and why](#hazard-logic-and-why)
7. [Assumptions](#assumptions)
8. [Security and performance](#security-and-performance)
9. [Known limitations](#known-limitations)
10. [What I'd improve with more time](#what-id-improve-with-more-time)
11. [AI tools used](#ai-tools-used)

---

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        UI["Next.js + React (Vercel)<br/>search · map · charts · table"]
    end
    subgraph Render["FastAPI (Render)"]
        R["routes.py<br/>validate · rate-limit · cache flow"]
        A["analysis.py"]
        C["cleaning.py"]
        H["heatwave.py"]
        T["trends.py"]
        W["weather_client.py"]
    end
    DB[("MongoDB Atlas<br/>raw_weather<br/>analysis_results (TTL)")]
    OM["Open-Meteo<br/>Archive + Geocoding APIs"]

    UI -- "GET /api/..." --> R
    R -- "1 cached result?" --> DB
    R -- "2 cached series?" --> DB
    R -- "3 else fetch" --> W --> OM
    R --> A --> C --> H --> T
    A -- "4 store result" --> DB
```

**Request flow for `GET /api/hazards/heatwave`:**

1. **Validate**: Pydantic checks every parameter (`schemas.py`). Bad input gets a `422` before any work starts.
2. **Result cache**: hash all parameters plus the analysis version and look up `analysis_results`. If found, return it (about 3 ms).
3. **Raw data cache**: look in `raw_weather` for a stored series that covers the needed dates. Only if there isn't one, fetch from Open-Meteo and store it.
4. **Compute**: clean the series, then threshold, events, yearly metrics, trends and insights. Store the result and return it.

**Backend layout:**

| File | Job |
|---|---|
| `app/main.py` | Creates the app: CORS, rate limiter, error handlers, DB connect/disconnect |
| `app/config.py` | All settings, from environment variables |
| `app/schemas.py` | Request validation and response models |
| `app/api/routes.py` | Endpoints and the cache flow above |
| `app/services/weather_client.py` | Open-Meteo calls: timeout, retries, error mapping |
| `app/services/cleaning.py` | Impossible values, gap filling, data-quality report |
| `app/services/heatwave.py` | Thresholds, event detection, yearly metrics (**pure functions**) |
| `app/services/trends.py` | Rolling mean, regression, Mann-Kendall, insight text (**pure functions**) |
| `app/services/analysis.py` | Calls the above in order and builds the JSON |
| `app/db/mongo.py` | Connection, indexes, the two caches |
| `scripts/analyze_city.py` | Command-line run of the analysis, with no server or DB |

The science (`cleaning`, `heatwave`, `trends`) never touches HTTP or the database. That's why it
can be unit-tested with tiny synthetic series.

**Frontend layout** (`frontend/src`, Next.js App Router):

| File | Job |
|---|---|
| `app/layout.tsx`, `app/page.tsx` | Server components: HTML shell, page title, global CSS |
| `components/HeatwaveApp.tsx` | The `'use client'` root: request state, loading/error/result views |
| `components/Controls.tsx` | The form; loads `MapPicker` with `next/dynamic` and `ssr: false` because Leaflet needs `window` |
| `components/LocationSearch.tsx`, `MapPicker.tsx` | City autocomplete; map click or box drawing |
| `components/MetricChart.tsx`, `SummaryCard.tsx`, `EventTable.tsx` | Results |
| `api/client.ts` | All HTTP calls to FastAPI |
| `types.ts` | Mirrors the backend response schema |
| `hooks/`, `format.ts` | `useDebounce`, `useChartColors`, text helpers |

The browser calls FastAPI directly. Next.js serves the UI only, with no API routes of its own,
because FastAPI is the single source of the API, its validation and its rate limits.

---

## Running locally

**Requirements:** Python 3.11+, Node 20+, and a MongoDB, either local or a free Atlas cluster.
The app also runs without MongoDB, just without caching (see [Assumptions](#assumptions)).

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # set MONGODB_URI if not using a local MongoDB
uvicorn app.main:app --reload      # http://localhost:8000/docs
pytest                             # 67 tests, no network or DB needed
```

Run the analysis for one city straight from the terminal:

```bash
python -m scripts.analyze_city --lat 19.07 --lon 72.88 --start 1980 --end 2023
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local         # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                        # http://localhost:3000
```

### Environment variables

| Variable | Where | Example | Notes |
|---|---|---|---|
| `ENVIRONMENT` | backend | `production` | In production, `CORS_ORIGINS=*` makes the app refuse to start |
| `CORS_ORIGINS` | backend | `https://my-app.vercel.app` | Comma-separated list |
| `MONGODB_URI` | backend | `mongodb+srv://user:pass@cluster.mongodb.net/` | **Secret** |
| `MONGODB_DB` | backend | `climate_hazards` | |
| `ANALYSIS_CACHE_TTL_DAYS` | backend | `30` | How long results are kept |
| `HTTP_TIMEOUT_SECONDS` | backend | `20` | Open-Meteo timeout |
| `HTTP_MAX_RETRIES` | backend | `2` | Retries on timeouts, 429 and 5xx |
| `RATE_LIMIT_ANALYSIS` | backend | `30/minute` | Per IP, on the analysis and CSV endpoints |
| `RATE_LIMIT_GEOCODE` | backend | `60/minute` | Per IP |
| `PYTHON_VERSION` | Render | `3.12.3` | Set in `render.yaml` |
| `NEXT_PUBLIC_API_URL` | frontend | `https://climate-hazard-api.onrender.com` | No trailing slash. Inlined at build time, so redeploy after changing it |

---

## Deploying

The order matters a little: the backend needs the frontend's URL for CORS, and the frontend
needs the backend's URL.

### 1. MongoDB Atlas (database)

1. Create a free account at <https://cloud.mongodb.com> and create an **M0 (free)** cluster.
2. **Database Access** → add a database user with a password, role *Read and write to any database*.
3. **Network Access** → add `0.0.0.0/0`. Render's free tier has no fixed outbound IP, so this is
   needed; the user and password are what protect the database.
4. **Connect → Drivers** → copy the connection string and put the password into it.
   This is your `MONGODB_URI`.

The collections and indexes (including the TTL index) are created automatically on first start.

### 2. Render (backend)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** → choose the repo. It reads `render.yaml`.
3. When asked, set `MONGODB_URI` (from step 1) and `CORS_ORIGINS` (use `http://localhost:3000`
   for now; you'll update it after step 3).
4. Wait for the deploy, then open `https://<your-service>.onrender.com/api/health`. You should see
   `{"status":"ok","database":"ok"}`.

### 3. Vercel (frontend)

1. In Vercel: **Add New → Project** → import the repo.
2. Set **Root Directory** to `frontend`. Vercel detects Next.js; no extra config is needed.
3. Add the environment variable `NEXT_PUBLIC_API_URL` = your Render URL (no trailing slash).
4. Deploy and copy the Vercel URL.

### 4. Connect them

1. In Render → your service → **Environment**: set `CORS_ORIGINS` to your Vercel URL
   (e.g. `https://heatwave-analyzer.vercel.app`) and save. Render redeploys.
2. Open the Vercel URL, search for "Mumbai" and run an analysis. The first request after the
   server has been idle takes 30–60 s (Render free tier cold start).

---

## API

All errors have the same shape, with a matching HTTP status:

```json
{ "error": { "code": "validation_error", "message": "start_year must be before end_year" } }
```

Error codes: `validation_error` (422), `rate_limited` (429), `not_found` (404),
`upstream_bad_request` (400), `upstream_unavailable` (502), `upstream_rate_limited` (503),
`internal_error` (500).

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | `{"status": "ok", "database": "ok" \| "unavailable"}` |
| `GET /api/geocode?q=Mumbai` | `[{name, country, admin1, lat, lon}]` |
| `GET /api/hazards/heatwave?...` | Full analysis (below) |
| `GET /api/hazards/heatwave/export.csv?...&table=yearly\|events` | The same analysis as CSV |

**Heatwave parameters**

| Param | Default | Allowed |
|---|---|---|
| `lat`, `lon` | n/a | −90..90, −180..180 |
| or `min_lat`, `max_lat`, `min_lon`, `max_lon` | n/a | box ≤ 2° × 2° |
| `start_year`, `end_year` | n/a | 1940..last full year; 10–85 years inclusive |
| `percentile` | 95 | 80–99 |
| `min_duration` | 3 | 2–10 days |
| `method` | `doy` | `doy` (day-of-year) or `annual` |
| `baseline_start`, `baseline_end` | see below | both or neither; ≥ 10 years |

**Response:** `metadata` (location and ERA5 grid cell, threshold, data quality, cached flag),
`yearly` (one row per year, with 5-year rolling means), `events` (start, end, duration, peak,
mean excess), `trends` (per metric: linear regression, Mann-Kendall, significance), and
`insights` (sentences). The full schema is on `/docs`.

---

## Data source and its limitations

Daily maximum 2 m temperature (`temperature_2m_max`) from the **Open-Meteo Historical Weather
API**, pinned to **ECMWF ERA5 reanalysis** (`models=era5`), 1940 onwards, on a 0.25° grid.
`timezone=auto` makes each "day" the location's local calendar day.

**Why pin `era5`:** Open-Meteo's default (`best_match`) blends several datasets, and the blend
changes over time. For Mumbai, the default series drifts against pure ERA5 by about 0.3 °C from
2017 onwards. For a *trend* analysis, a step like that can look like climate change, so one
consistent dataset is worth more than finer resolution. It can be changed via `OPEN_METEO_MODEL`.

What that means for the results:

- **It is a grid, not a weather station.** ERA5 cells are about 25 km across. Each value is an area average, so it is smoother than a thermometer: peak temperatures
  are lower, and city-centre heat (the urban heat island) is largely missing. The response
  reports the grid cell actually used (`grid_lat`, `grid_lon`).
- **It is a model blended with observations.** It is consistent over time, which is good for
  trends, but early decades rest on fewer observations, especially outside Europe and North
  America.
- **It is essentially gap-free.** That's why the cleaning step rarely changes anything in
  practice. It's there because the code shouldn't assume a perfect source.
- **Temperature only.** No humidity, so this measures heat, not heat stress
  (wet-bulb temperature or heat index).

---

## Hazard logic and why

### 1. Cleaning (`cleaning.py`)

| Step | Rule | Why |
|---|---|---|
| Complete the calendar | Reindex to every day; absent dates become NaN | Event detection assumes "next row = next day" |
| Impossible values | Tmax < −90 °C or > 60 °C becomes NaN | Outside the world records (−89 °C, +57 °C), so it's a data error, not weather |
| Short gaps | Gaps of ≤ 2 days are linearly interpolated | One or two days barely change the statistics, and it stops a single missing day from splitting a heatwave |
| Long gaps | Left as NaN | Inventing a week of temperatures could create or hide a heatwave |
| Edges | Never extrapolated | There's nothing on one side to interpolate from |
| Quality report | Per year: % missing, % filled, % still missing, count of impossible values | Shown in the UI. Years still missing > 10% are flagged, because heatwaves could hide in the gaps |

A day that is still missing **breaks** a heatwave: `NaN > threshold` is `False`.

### 2. Threshold (`heatwave.py`)

**95th percentile of daily Tmax from a fixed baseline period.**

- **Percentile, not a fixed temperature.** 35 °C is ordinary in Delhi and extreme in London.
  A percentile means "unusually hot *for this place*", so any location works.
- **Fixed baseline.** If the threshold were computed from the whole period, a warming trend would
  raise it and partly hide the trend itself. A fixed baseline gives every year the same yardstick.
- **Default baseline:** 1961–1990 (the WMO reference period) when the requested range covers it,
  otherwise the first 30 years of the range (the whole range if it's shorter). A custom baseline
  can be passed, even outside the range; the extra years are then fetched.
- **Day-of-year method (default).** Each calendar day gets its own threshold: the percentile of
  all baseline days within ±7 days of it (15 days × 30 years = 450 values). This catches an
  unusually hot spell in any season, such as Mumbai's October heat, which an annual threshold
  would ignore because October is never as hot as May. It's the same approach as the
  ETCCDI/CTX90pct-style indices used in climate research.
  - Implementation: every observation is copied into the 15 calendar days around it, then one
    `groupby().quantile()` runs. No Python loop over days.
  - Leap years: 29 Feb shares a slot with 28 Feb, so 1 March is always compared with 1 March.
  - The window wraps around New Year.
- **Annual method (option).** One percentile of all baseline days. Simpler, and it only
  identifies hot-season heatwaves.

### 3. Event detection

A heatwave is **≥ `min_duration` (default 3) consecutive days with Tmax strictly above the
threshold**. It's vectorised: mark hot days, give each run of consecutive identical values an
id with `(hot != hot.shift()).cumsum()`, group by that id, and keep the runs that are long enough.

### 4. Yearly metrics

| Metric | Definition |
|---|---|
| Events | Number of heatwaves starting that year |
| Heatwave days | Sum of their durations |
| Longest event | Longest of them (0 if none) |
| Mean intensity | Day-weighted mean of (Tmax − threshold) over their days. **Empty, not 0, when there were no heatwaves** |
| Max Tmax | Hottest day of the year |

A heatwave that crosses New Year is counted entirely in the year it **starts**, so it's never
counted twice.

### 5. Trends (`trends.py`)

| Statistic | Why |
|---|---|
| **5-year centred rolling mean** | Shows the shape of change through year-to-year noise. It needs at least 3 values, so edge years use shorter windows |
| **Linear regression** (slope per decade, p-value, R²) | Familiar, and gives the dashed trend line on the charts |
| **Mann-Kendall test + Sen's slope** | **This decides "significant".** Heatwave counts are skewed, often zero, and dominated by a few extreme years, which breaks regression's assumptions. Mann-Kendall only asks whether later years tend to be higher than earlier ones, and Sen's slope is the median of all pairwise slopes, so one extreme year can't dominate |

Sen's slope is computed against the actual years (`scipy.stats.theilslopes`), so years with
no value (intensity without a heatwave) don't distort it.

### 6. Insight text

- It compares **the first decade with the last decade**, not single years. A single year is
  noise, and picking the endpoints could support almost any story. Ranges shorter than 20 years
  are compared half against half.
- **% change only when it means something.** It's shown only for counts, and only when the
  earlier average is ≥ 1. Going from 0.2 to 0.8 events a year is "+300%" but less than one event,
  so in that case the absolute change is given instead.
- **It always states significance**, with the Mann-Kendall p-value and Sen's slope. A
  non-significant change is described as possibly natural variation.
- Example (Mumbai, 1980–2023):
  > Heatwave days rose from an average of 4.0 days/year (1980–1989) to 28.5 days/year (2014–2023),
  > a change of +612%. The upward trend is statistically significant (Mann-Kendall p < 0.001;
  > Sen's slope +5.00 days/year per decade).

### Extending to other hazards

A new hazard would be a new `services/<hazard>.py` (pure detection and metrics), a query model in
`schemas.py`, and a route. `cleaning.py`, `trends.py`, `weather_client.py` and both caches are
reused as they are: the cache key already includes `"hazard"`. In the UI, the hazard dropdown
already lists drought and heavy rain, disabled.

---

## Assumptions

Choices I made where the brief left room:

1. **Baseline:** 1961–1990 if inside the requested range, otherwise the first 30 years of the
   range (or the whole range if it's shorter). It's configurable per request.
2. **Bounding box → centre point.** Averaging a 3×3 grid would smooth daily extremes and change
   what "heatwave" means (a regional-mean heatwave). The centre keeps the box and point analyses
   identical and costs one API call instead of nine. The box is capped at 2° × 2°.
3. **"Above" the threshold means strictly greater than.**
4. An event is attributed **entirely to the year it starts in**.
5. A heatwave already in progress at the start or end of the range is counted with the part that
   falls inside the range.
6. **Mean intensity is empty** in years without heatwaves and those years are left out of its
   trend, because "no heatwave" is not "a heatwave of zero intensity".
7. **Significance is judged by Mann-Kendall** at p < 0.05. Regression is shown alongside it.
8. Years with > 10% of days still missing after cleaning are **flagged, not dropped**.
9. **Year range:** both years inclusive, so 1991–2020 is 30 years. It must be 10–85 years. The
   last allowed year is the last full calendar year.
10. **Coordinates are rounded to 2 decimals** (~1 km), far finer than the ~25 km grid. It improves
    cache hits and changes no results.
11. **The cache fails open:** if MongoDB is unreachable, the API logs a warning and computes the
    answer without caching instead of returning an error. Results are still stored and read from
    MongoDB whenever it is available.
12. **Raw-data cache reuse:** any stored series whose date range *contains* the requested range is
    reused (sliced). Partially overlapping ranges are fetched again rather than stitched together.
13. **Validation errors use HTTP 422**, which is FastAPI's convention.
14. **PDF export uses the browser's print dialog** (Save as PDF) with a print stylesheet. That
    avoids adding a PDF library.
15. **MongoDB driver:** PyMongo's built-in async client instead of Motor, which is deprecated in
    its favour.
16. **Data source pinned to pure ERA5** (`models=era5`) for a consistent series over time. See
    [Data source](#data-source-and-its-limitations).
17. Dependencies I added beyond the brief: `uvicorn` (the server), `pydantic-settings` (config),
    `@types/leaflet` (TypeScript types only). The frontend uses **Next.js** (App Router) instead of plain React + Vite.

---

## Security and performance

**Input:** every parameter has type, range and cross-field checks in Pydantic models. The geocode
query is length-limited (2–100 characters), whitespace-normalised, and restricted to letters (any
language), digits, spaces and `- ' . , ( )`.

**Rate limiting** (slowapi, per IP): 30/min on the analysis and CSV endpoints, 60/min on geocode.
uvicorn runs with `--proxy-headers`, so the limit applies to the real client IP behind Render's proxy.

**CORS:** only the origins in `CORS_ORIGINS`, and only `GET`. The app refuses to start in
production if `*` is configured.

**Secrets:** only in environment variables. `.env` is git-ignored, and `.env.example` documents
every variable.

**Errors:** one JSON shape for every failure. Unexpected exceptions are logged on the server and
the client gets a generic 500, never a stack trace.

**External calls:** 20 s timeout. Two retries with exponential backoff (1 s, 2 s) on timeouts,
network errors, 429 and 5xx. Other 4xx responses are not retried because the request itself is
wrong. Each failure maps to a clear error code.

**Frontend headers** (`next.config.ts`): `nosniff`, `DENY` framing, strict referrer policy.

**Performance:**
- Two cache layers: a repeat request takes about 3 ms; a new percentile on cached data takes about 50 ms.
- All heavy work is vectorised pandas or numpy. The only loop is over at most 85 years when
  building the JSON.
- The CPU-bound analysis runs in a worker thread (`asyncio.to_thread`) so it doesn't block other requests.
- Raw series are stored as a compact array with only a start date, not one document per day.
- TTL index: MongoDB deletes old results by itself.
- Frontend: the search is debounced (350 ms), stale requests are cancelled with `AbortController`,
  and a health ping is sent on page load to start waking a sleeping server early.

---

## Known limitations

- **ERA5 resolution and urban heat:** see [Data source](#data-source-and-its-limitations).
- **Tmax only:** this ignores hot nights (Tmin) and humidity, which matter a lot for health impacts.
- **Percentile thresholds in a warming climate:** an increase in heatwave count partly reflects
  mean warming, not just more variable extremes. That's a real signal, but it's worth saying.
- **Mann-Kendall assumes independent years.** Strong year-to-year persistence (e.g. ENSO) can make
  p-values too optimistic. The Hamed-Rao modified test would correct for it.
- **Several tests at once:** five metrics tested at p < 0.05 means about a 23% chance that at least
  one looks significant by luck.
- **The rate limiter is in memory**, per process. It resets on restart and isn't shared between
  instances. Trusting `X-Forwarded-For` from any proxy (`--forwarded-allow-ips="*"`) means a client
  could spoof its IP if it could reach uvicorn directly. On Render only the proxy can.
- **Cold starts:** Render's free tier sleeps after about 15 minutes idle, so the first request
  takes 30–60 s.
- Two identical requests arriving at the same moment both fetch from Open-Meteo. The deterministic
  `_id` prevents duplicate documents.
- The frontend has no automated tests. First-load JS is about 217 kB; the Leaflet map loads separately afterwards.
- Boxes that cross the antimeridian (±180°) aren't supported.

---

## What I'd improve with more time

1. **More hazards** (drought via SPI from precipitation, heavy rain via R95p) using the extension
   path above.
2. **Better heat metrics:** a Tmin / hot-nights analysis, humidity-aware indices (heat index,
   wet-bulb), and the Excess Heat Factor.
3. **Statistics:** the Hamed-Rao modified Mann-Kendall test, confidence intervals on Sen's slope,
   and a false-discovery-rate correction.
4. **Regional analysis:** average a grid of points inside the box as an option, or show a map of
   per-cell trends.
5. **Cache:** stitch partially overlapping raw ranges; deduplicate concurrent fetches.
6. **Tests:** Vitest + React Testing Library for components; one Playwright end-to-end test;
   CI (GitHub Actions) running pytest, lint and build on every push.
7. **Operations:** a Redis-backed rate limiter, structured logging, and a paid instance to avoid cold starts.
8. **UX:** add a threshold-curve chart for the day-of-year method, a
   shareable URL with the parameters, and a side-by-side comparison of two cities.

---

## AI tools used

_To be filled in: which tools, what for, and how the output was checked._
