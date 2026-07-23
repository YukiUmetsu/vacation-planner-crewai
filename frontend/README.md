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

**Auth gate (live + Cognito):** when `VITE_COGNITO_*` is set and demo is off, the app shows a landing page with Sign in / Sign up and any enabled social providers (`VITE_COGNITO_IDENTITY_PROVIDERS`). You cannot open the trip wizard until Hosted UI login completes. Deploy with `./scripts/deploy.sh` (bakes Cognito + provider list from Terraform).

Without Cognito env, live mode still uses the Vite DEV `X-Dev-User-Sub` header against a local `AUTH_MODE=dev` API.

### Tests

```bash
npm test
```

## Design

Mockups (approved): [`docs/mockups/`](./docs/mockups/)

Theme: ocean teal + sand, Newsreader + DM Sans (`src/index.css`). Energy load caps: see [`docs/PLANNING_QUALITY.md`](../docs/PLANNING_QUALITY.md).

## Status vs still to wire

**Done:** Tailwind theme, wizard shell, demo App (cities/days/profile), create + propose/confirm/plan-next-day live mutations (`VITE_USE_DEMO_DATA=false`), profile `localStorage`, city day-range helpers, place remove-by-index, Vitest coverage for API/create/remove/a11y, Cognito PKCE Hosted UI (landing + provider pick + live auth gate).

**Still to wire (you):** Trip list UI can call `listTrips()` when you add a picker. Enable Facebook/Google via Terraform secrets so landing social buttons appear after redeploy.

## Layout

```text
src/
  auth/          # Cognito Hosted UI: landing, PKCE, oauth, session, AuthBar, /callback
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
scripts/deploy.sh
```
