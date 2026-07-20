# vacation-planner-models

Shared Pydantic models (`Place`, `CityRoute`, `DayPlan`, `Trip`) and `place_key` helpers.

```bash
cd agent/models
uv sync --extra dev
uv run pytest ../tests
```

Import:

```python
from vacation_planner_models import DayPlan, CityRoute, make_place_key
```

Crews depend on this package via an editable uv path (see `crews/day_plan/pyproject.toml`).
