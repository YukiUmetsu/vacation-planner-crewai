# suggest_city

Additive overnight-city recommendation (non-persisting).

| Agent | Tools | Role |
| --- | --- | --- |
| `suggest_city_agent` | Serper + `custom:amap_place_search` | Research + emit `CitySuggestionResult` |

**API:** `POST /trips/{id}/suggest-city` with optional `{ cities, hint, count }` → `{ candidates }`.  
Does not write ROUTE; FE inserts via `addCityStop` and user confirms.

**Prompt version:** `2026-07-26.1`
