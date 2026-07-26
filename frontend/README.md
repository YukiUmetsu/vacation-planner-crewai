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
- **Cities:** adjust nights (day ranges recompute); **Remove** a stop; city photos; **Add city → Hiroshima** for the feasibility warning; **Propose** shows a destination loading canvas (demo ~11s)

### Live create flow (end-to-end local)

**Easiest:** from the repo root, one command starts DynamoDB + API + this SPA:

```bash
./scripts/dev.sh
```

Or manually — Terminal 1 (API + DynamoDB):

```bash
cd backend
docker compose up -d
export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
uv run python scripts/local_api.py
```

Terminal 2 — SPA (live mode, no Cognito env vars):

```bash
cd frontend
VITE_USE_DEMO_DATA=false npm run dev
```

Open http://localhost:5173 and walk through:

1. Fill **Create trip** → submit. The app jumps to Cities and starts proposing immediately (loading canvas with photos / quotes / questions).
2. With `CREW_MODE=fake`, propose finishes quickly and shows cities with photos — **Remove** any stop, tweak nights, then **Confirm route**.
3. Days opens and **Plan next day** starts automatically for day 1.
4. Reload later: **Your trips** on Details lists saved plans; incomplete trips auto-resume into the wizard. Use **+ New trip** to start blank.

Optional: set `CREW_MODE=agentcore` against a deployed runtime (needs `AGENT_RUNTIME_ARN` + AWS creds) to exercise the real city-route crew locally.

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

## Current limitations

- Social login buttons only appear when Facebook/Google IdPs are enabled via Terraform secrets and the SPA is redeployed with that provider list
- Demo mode does not call `listTrips` / Cognito — use live mode (`VITE_USE_DEMO_DATA=false`) to exercise save / resume

## Roadmap / planned improvements

- Richer profile sync (server-backed prefs beyond local cache where still client-only)
- Demo and live parity for add/remove place where product rules allow

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
    DetailsStep.tsx / ProfileScreen.tsx / TripStatusBanner.tsx / TripSwitcher.tsx
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
