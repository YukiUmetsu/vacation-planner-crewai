# Single-call day plan baseline

One agent + tools emits `DayPlanWithQuality` in a single structured call.

Tools match `day_plan` researcher: `SerperDevTool` + `custom:amap_place_search`.

Used for the offline orchestration experiment against sequential
`day_plan` (researcher → planner → reviewer). Same model, schema, and
eval scorers — only the orchestration differs.

See `docs/PLANNING_QUALITY.md` (orchestration experiment) and
`agent/evals/README.md` (`--compare-orchestration`).
