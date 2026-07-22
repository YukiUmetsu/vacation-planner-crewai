# Frontend

Vite + React 19 + TypeScript + TanStack Query + Tailwind CSS v4.

Talks only to the **backend** API (`/api/...` or `VITE_API_URL`). Local `AUTH_MODE=dev` uses `X-Dev-User-Sub` (sent only in Vite DEV builds).

Env vars: [`docs/ENVIRONMENT.md`](../docs/ENVIRONMENT.md) (frontend section + deploy).

## Run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**Demo mode is on by default** (`VITE_USE_DEMO_DATA` unset / not `false`): click Details / Cities / Days with sample Japan data — no API needed.

- **Days:** click a place for detail sheet (cost, hours, map, why suggested, watch-outs); min total time (incl. travel); **Suggest a place** (live API); **Add/Remove** in demo only
- **Profile** (header): preferences, energy level (1–5 signal bars), interests, places you’ve been
- **Cities:** adjust nights (day ranges recompute); **Add city → Hiroshima** for the feasibility warning

### Live create flow

```bash
VITE_USE_DEMO_DATA=false npm run dev
```

Requires a local API on `http://127.0.0.1:8787` (Vite proxies `/api`). Start it with:

```bash
cd backend
export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
uv run python scripts/local_api.py
```

For deployed backends set `VITE_API_URL` (e.g. `https://api.example.com`) and skip the Vite proxy.

### Tests

```bash
npm test
```

## Design

Mockups (approved): [`docs/mockups/`](./docs/mockups/)

Theme: ocean teal + sand, Newsreader + DM Sans (`src/index.css`). Energy load caps: see [`docs/PLANNING_QUALITY.md`](../docs/PLANNING_QUALITY.md).

## Status vs still to wire

**Done:** Tailwind theme, wizard shell, demo App (cities/days/profile), create + propose/confirm/plan-next-day live mutations (`VITE_USE_DEMO_DATA=false`), profile `localStorage`, city day-range helpers, place remove-by-index, Vitest coverage for API/create/remove/a11y.

**Still to wire:** Cognito Hosted UI sign-in (live API still uses `AUTH_MODE=dev` locally). Trip list UI can call `listTrips()` when you add a picker. Profile GET/PUT `/profile` is wired from the wizard (falls back to localStorage if the API is down).

## Layout

```text
src/
  api/           # http.ts, trips.ts (+ tests)
  types/trip.ts
  hooks/         # useTripWizard (demo + live wizard state)
  lib/           # dayPlaces, cityRoute, liveTrip, profileStorage (+ tests)
  demo/          # static Japan trip / profile / place details
  components/
    WizardLayout.tsx
    DetailsStep.tsx / ProfileScreen.tsx / TripStatusBanner.tsx
    CreateTripForm.tsx
    TripGist.tsx / TripPanel.tsx
    cities/      # Cities chrome
    days/        # Days chrome + place detail
    profile/     # Profile page
  test/setup.ts
  App.tsx
  index.css
docs/mockups/
```
