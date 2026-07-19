# Backend

HTTP API (API Gateway + Lambda): verify Cognito JWT, read/write DynamoDB, invoke AgentCore.

The frontend talks only to this API — never to AgentCore or DynamoDB directly.

## Planned routes

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/trips` | Create trip meta |
| `POST` | `/trips/{id}/propose-cities` | Propose city route |
| `PUT` | `/trips/{id}/cities` | Confirm / edit city route |
| `POST` | `/trips/{id}/plan-next-day` | Plan + persist next day |
| `GET` | `/trips/{id}` | Trip + route + days |
| `GET` | `/trips` | List current user’s trips |

## Layout

```text
src/
  handler.py          # Lambda / HTTP entry
  auth.py             # Cognito JWT verify
  routes/trips.py
  db/                 # single-table helpers + repository
  agentcore/client.py
  services/           # dedupe, trip orchestration
  models/             # Pydantic (align with docs/DATA_MODEL.md)
```

Scaffold only — not deployed yet.
