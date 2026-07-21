# Frontend

Vite + React 19 + TypeScript + TanStack Query + Tailwind CSS v4.

Talks only to the **backend** API (`/api/...`). Local `AUTH_MODE=dev` uses `X-Dev-User-Sub`.

## Run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**Demo mode is on by default** (`VITE_USE_DEMO_DATA` unset / not `false`): click Details / Cities / Days with sample Japan data — no API needed.

- **Days:** click a place for detail sheet (cost, hours, map, why suggested, watch-outs); **Add place** / **Suggest a place**
- **Profile** (header): preferences, interests, places you’ve been
- Cities: **Add city → Hiroshima** for the feasibility warning

### Live create flow

```bash
VITE_USE_DEMO_DATA=false npm run dev
```

Requires a local API on `http://127.0.0.1:8787` (Vite proxies `/api`). For deployed backends set `VITE_API_URL` (e.g. `https://api.example.com`) and do not rely on the Vite proxy.

```bash
npm test
```

## Design

Mockups (approved): [`docs/mockups/`](./docs/mockups/)

Theme: ocean teal + sand, Newsreader + DM Sans (`src/index.css`).

## What’s scaffolded vs yours to wire

**Done (agent):** Tailwind, `WizardLayout`, styled create form + trip gist, presentational `CitiesPanel` / `DaysPanel` (thumbs, hover popover, add city, feasibility banner).

**You (learning):** step state; propose/confirm/add-city + feasibility; plan-next-day + invalidate trip query. Follow `LEARNING` comments in [`src/App.tsx`](./src/App.tsx).

## Layout

```text
src/
  api/           # http.ts, trips.ts
  types/trip.ts
  components/
    WizardLayout.tsx
    CreateTripForm.tsx
    TripGist.tsx / TripPanel.tsx
    cities/      # presentational Cities chrome
    days/        # presentational Days chrome
  App.tsx
  index.css
docs/mockups/
```
