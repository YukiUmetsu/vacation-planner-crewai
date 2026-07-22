# Offline crew evals

Plumbing for golden-set checks against crew JSON outputs. **No AWS required** for harness tests.

Traveler energy hour caps (for future scorers): [`docs/PLANNING_QUALITY.md`](../../docs/PLANNING_QUALITY.md).

## Layout

| Path | Purpose |
| --- | --- |
| `case.py` / `harness.py` | Load fixtures + run cases (done) |
| `scorers.py` | Place/city count, keys, dedupe, nights checks |
| `fixtures/*.json` | Case inputs + expected hints (add more goldens as needed) |
| `test_harness.py` | Smoke tests for loading / scorers / producer errors |

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

## CLI

```bash
cd agent
uv run python -m evals            # score fixtures that have sibling *.output.json
uv run python -m evals --live     # call crew_kickoff (needs credentials)
```

Offline mode **skips** cases without `fixtures/<id>.output.json` (prints `SKIP`). A golden for `day_plan_example_shape` is included so the default command exits 0.

Optional offline outputs: `fixtures/<id>.output.json` (skipped by the case loader; used only as eval input).

## Extending

Add fixtures with `expected` keys such as `min_places` / `max_places` / `forbidden_place_keys` (day) or `min_cities` / `max_cities` (route). Pair with `*.output.json` for offline CLI runs without `--live`.
