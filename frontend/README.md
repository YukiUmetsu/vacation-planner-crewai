# Frontend

Vite React TypeScript SPA: Cognito Hosted UI (Google), trip wizard, city-route confirm, day timeline.

Talks only to the **backend** API. Prefs/summaries can use `localStorage` for MVP personalization.

## Layout

```text
src/
  api/                 # backend client
  auth/                # Cognito helpers
  features/
    trips/
    city-route/
    day-plan/
  components/
  lib/                 # localStorage, etc.
```

## Local (when wired)

```bash
npm install
npm run dev
```

Scaffold only — flesh out before first UI work.
