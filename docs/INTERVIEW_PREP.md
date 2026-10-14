# Interview prep: likely questions, by phase

Short answers you can expand on. File references point to where the answer lives in the code.

---

## Phase 1: Setup (`main.py`, `config.py`)

**Why `@lru_cache` on `get_settings()`?**
The environment is read once and every module shares one `Settings` object.

**Where does a setting's value come from?**
First a real environment variable, then `.env`, then the default in `config.py`. Field names
match variables case-insensitively (`MONGODB_URI` fills `mongodb_uri`).

**What does CORS protect, and what doesn't it protect?**
It stops *other websites' JavaScript* from reading our API's responses in a user's browser.
It does nothing against curl or scripts, which is why rate limiting exists too.

**Why does the app refuse to start with `CORS_ORIGINS=*` in production?**
Failing loudly at deploy time is better than quietly running insecurely.

**What is the `lifespan` function?**
Code that runs once at startup (connect to MongoDB, create indexes) and once at shutdown (close it).

---

## Phase 2: Data (`weather_client.py`, `cleaning.py`)

**Why retry 429 and 5xx but not 400?**
429 and 5xx are temporary (busy or broken server), so a retry can succeed. A 400 means our
request is wrong, and sending it again gives the same answer.

**Why exponential backoff (1 s, 2 s)?**
Retrying immediately adds load to a struggling server. Waiting longer each time gives it room
to recover.

**Why not `interpolate(limit=2)`?**
On a 5-day gap it would still fill the first 2 days. We measure each gap's full length first
(`fill_short_gaps`) and fill only gaps of 2 days or fewer.

**How does a missing day break a heatwave?**
`NaN > threshold` is `False` in pandas, so a missing day is "not hot" and ends the run.

**Why reindex to a complete daily calendar?**
Event detection assumes the next row is the next day. If a date were silently absent, two
separate hot spells could merge into one.

**Why pin `models=era5`?**
Open-Meteo's default blends datasets that change over time. For Mumbai it shifts by about 0.3 °C
around 2017, which could create a fake trend. A consistent dataset matters more than resolution
for trends.

---

## Phase 3: Climate logic (`heatwave.py`, `trends.py`)

**Why a percentile instead of a fixed temperature like 40 °C?**
A percentile is relative to local climate. 35 °C is normal in Delhi and extreme in London, so a
percentile works anywhere.

**Why a fixed baseline instead of the whole period?**
If the threshold included recent hot years, it would rise with warming and hide part of the
trend we're trying to measure.

**Explain the day-of-year threshold.**
Each calendar day gets the 95th percentile of baseline Tmax within ±7 days of it, across all
baseline years. It catches unusually hot spells in any season (e.g. Mumbai in October). In code,
each value is copied into its 15 neighbouring days, then there's one `groupby().quantile()`.

**How does the run detection work?**
`hot != hot.shift()` is True wherever hot/not-hot flips. `cumsum()` turns those flips into a run
id. Group by the id, keep the hot runs, and count each run's length.

**Why Mann-Kendall for significance instead of regression's p-value?**
Heatwave counts are skewed, often zero, and driven by a few extreme years. Regression assumes
normal residuals. Mann-Kendall is rank-based, so it makes no distribution assumption and one
outlier can't dominate it.

**Why is mean intensity empty in years without heatwaves?**
Zero would mean "heatwaves happened, at zero intensity", which is false. It would also drag the
trend down.

**Why decade averages, and why sometimes no percentage?**
Single years are noisy and easy to cherry-pick. A percentage from a near-zero base (0.2 → 0.8)
exaggerates, so below an average of 1 the absolute change is shown.

---

## Phase 4: API and MongoDB (`routes.py`, `schemas.py`, `mongo.py`)

**Walk me through a request.**
Validate (Pydantic) → result cache → raw-data cache → else fetch → compute in a thread → store →
return (`get_heatwave_analysis`).

**What's in the cache key, and why the version?**
Every parameter, the rounded coordinates, the hazard name and `ANALYSIS_VERSION`. If I change the
logic I bump the version, and old cached results are no longer served.

**What does the TTL index do?**
MongoDB deletes `analysis_results` documents about 30 days after `created_at`, by itself. A
background task runs about every 60 s, so deletion isn't instant.

**What happens if MongoDB is down?**
The cache fails open: a warning is logged and the request is computed without caching.
`serverSelectionTimeoutMS=3000` keeps that from hanging.

**Why `asyncio.to_thread` for the analysis?**
pandas work is CPU-bound. In an `async` handler it would block the event loop, and with it every
other request, until it finished.

**How does rate limiting work behind Render's proxy?**
slowapi counts per IP. `--proxy-headers` makes uvicorn take the real client IP from
`X-Forwarded-For`; otherwise every user would share the proxy's IP and its limit.

---

## Phase 5–6: Frontend (Next.js: `app/`, `components/`)

**Why Next.js, and what does it do for this app?**
It renders the page shell on the server, so the page arrives as real HTML and is fast to show.
It also handles routing, builds and optimisation, and deploys to Vercel with no config. The
interactive part runs in the browser as a client component.

**What does `'use client'` mean?**
`HeatwaveApp.tsx` and everything it imports run in the browser, where hooks, state and events
work. `page.tsx` and `layout.tsx` stay server components. Client components are *also*
pre-rendered on the server once, so their code must not touch `window` during render.

**Why is the map loaded with `dynamic(..., { ssr: false })`?**
Leaflet reads `window` as soon as it's imported, which crashes the server render. `ssr: false`
skips it on the server and loads it in the browser, showing "Loading map…" until then. It also
keeps Leaflet out of the first page load.

**Why does `useChartColors` start in light mode?**
The server can't know the user's OS theme. It renders light, then an effect switches to the
real setting in the browser. Reading `window` in the initial state would crash on the server.

**Why `NEXT_PUBLIC_API_URL`, and is it a secret?**
Only variables starting with `NEXT_PUBLIC_` reach browser code. They're inlined at build time,
so changing one needs a redeploy. It's a public URL; real secrets live only in the backend.

**Why not use Next.js API routes?**
FastAPI is already the API, with its validation, rate limiting and caching. A Next.js proxy in
front of it would add a second hop and a second place for bugs, with no gain here.

**How does the debounced search work?**
`useDebounce` updates its value only after 350 ms without typing. The search effect depends on
that value, and its cleanup aborts the previous request, so results can't arrive out of order.

**How do you avoid a stale result overwriting a newer one?**
Each analysis gets an `AbortController`. Starting a new one aborts the old one, and an aborted
request never updates state.

**How do CSV and PDF export work?**
CSV is a plain link; the backend's `Content-Disposition: attachment` triggers the download. PDF
is `window.print()` with a print stylesheet that hides the controls.

---

## Phase 7–8: Deployment

**Why `0.0.0.0/0` in Atlas network access?**
Render's free tier has no fixed outbound IP. The database is protected by user and password
instead. A paid plan would allow IP allow-listing.

**Why does the first request take so long?**
Render's free tier sleeps after about 15 minutes idle. The page pings `/api/health` on load to
start waking it, and the loading message explains the delay.

**What would you change for production at scale?**
A Redis-backed rate limiter and cache-lock, structured logging, CI, a paid instance (no cold
starts), and frontend tests.
