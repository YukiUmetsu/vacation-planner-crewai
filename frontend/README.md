# Frontend

Vite + React 19 + TypeScript + TanStack Query + Tailwind CSS v4.

Talks only to the **backend** API (`/api/...` or `VITE_API_URL`). Local `AUTH_MODE=dev` uses `X-Dev-User-Sub` (sent only in Vite DEV builds).

## Run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**Demo mode is on by default** (`VITE_USE_DEMO_DATA` unset / not `false`): click Details / Cities / Days with sample Japan data — no API needed.

- **Days:** click a place for detail sheet (cost, hours, map, why suggested, watch-outs); min total time (incl. travel); **Add place** / **Suggest a place** / **Remove**
- **Profile** (header): preferences, interests, places you’ve been
- **Cities:** adjust nights (day ranges recompute); **Add city → Hiroshima** for the feasibility warning

### Live create flow

```bash
VITE_USE_DEMO_DATA=false npm run dev
```

Requires a local API on `http://127.0.0.1:8787` (Vite proxies `/api`). For deployed backends set `VITE_API_URL` (e.g. `https://api.example.com`) and skip the Vite proxy.

### Tests

```bash
npm test
```

## Design

Mockups (approved): [`docs/mockups/`](./docs/mockups/)

Theme: ocean teal + sand, Newsreader + DM Sans (`src/index.css`).

## Status vs still to wire

**Done:** Tailwind theme, wizard shell, demo App (cities/days/profile), create form + `TripPanel` for live mode, city day-range helpers, place remove-by-index, Vitest coverage for API/create/remove/a11y.

**Still to wire (live API):** propose/confirm cities mutations, plan-next-day + query invalidation, Cognito sign-in. Follow `LEARNING` comments where present.

## Layout

```text
src/
  api/           # http.ts, trips.ts (+ tests)
  types/trip.ts
  lib/           # dayPlaces, cityRoute helpers (+ tests)
  demo/          # static Japan trip / profile / place details
  components/
    WizardLayout.tsx
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
