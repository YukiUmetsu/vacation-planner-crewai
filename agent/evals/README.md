# Offline crew evals

Plumbing for golden-set checks against crew JSON outputs. **No AWS required** for harness tests.

## Layout

| Path | Purpose |
| --- | --- |
| `case.py` / `harness.py` | Load fixtures + run cases (done) |
| `scorers.py` | **LEARNING** — implement real failure checks |
| `fixtures/*.json` | **LEARNING** — add goldens; one example shape is included |
| `test_harness.py` | Smoke tests for loading / producer errors |

## Fixture shape

```json
{
  "id": "day_plan_tokyo_day1",
  "crew": "day_plan",
  "inputs": { "overnight_city": "Tokyo", "day_index": 1, "already_visited": [] },
  "expected": { "min_places": 3, "max_places": 6, "forbidden_place_keys": [] }
}
```

Files starting with `_` are ignored.

## Run harness tests

From `agent/` (uses the top-level agent venv):

```bash
cd agent
uv sync
uv run pytest evals/test_harness.py -q
```

## LEARNING next steps

1. Implement `score_day_plan` / `score_city_route` in `scorers.py` (schema, `place_key`, dedupe vs `already_visited`, place count).
2. Add fixtures that encode pass/fail expectations.
3. Optional: a CLI that calls `crew_kickoff.run_crew` as the producer (live; keep out of default CI).
