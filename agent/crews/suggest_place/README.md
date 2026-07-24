# Suggest place crew

Research → one `Place` to append to an existing day.

| Agent | Role |
| --- | --- |
| `suggest_place_researcher` | Serper: 2–4 candidates with status/hours and minute estimates |
| `suggest_place_composer` | One structured `Place` under `remaining_minutes` |

Hard rules in prompts (mirrored by API `validate_suggested_place`):

- not in `already_visited`
- not `operational_status=closed`
- not closed on `{date}` weekday when `closed_weekdays` known
- `estimated_minutes + travel_minutes_from_previous <= remaining_minutes`

Inputs: `overnight_city`, `date`, `day_index`, prefs/energy, `already_visited`, `current_places_json`, `remaining_minutes`, `next_order_in_day`, `food_crawl_mode`, `prefer_non_food`, `min_non_food_places`.
