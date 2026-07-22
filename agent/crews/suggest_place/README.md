# Suggest place crew

Research → one `Place` to append to an existing day.

| Agent | Role |
| --- | --- |
| `suggest_place_researcher` | Serper research for an extra stop |
| `suggest_place_composer` | Structured `Place` within `remaining_minutes` |

Inputs: `overnight_city`, `date`, `day_index`, prefs/energy, `already_visited`, `current_places_json`, `remaining_minutes`, `next_order_in_day`.

The API applies hard gates (`validate_suggested_place`) before persisting.
