# Application data model

Shared shape for CrewAI `output_pydantic`, API responses, and DynamoDB item payloads. One schema everywhere avoids drift between the planner agents, the BFF, and the UI.

## Why this shape

### Domain models mirror the product flow

Planning is intentionally staged:

1. **Trip** — dates, origin/destination, preferences
2. **CityRoute** (when destination is a country/region) — which cities and how many nights, before any day detail
3. **DayPlan** — one day at a time, with a list of **Place** stops

That maps to how users decide (“Japan for 10 days” → “Tokyo then Kyoto” → “what do I do on day 3?”) and to how the crew is invoked (small prompts with prior context, not one giant 14-day generation).

### Why places are nested on the day (not their own table rows)

A day’s itinerary is almost always read and shown together. Nesting `places[]` on the DAY item means one read returns a renderable day. We do not need “all museums for user X” or cross-trip place search in the MVP, so promoting every Place to its own item would add write amplification and join logic with no access-pattern payoff.

Cross-day uniqueness still matters, so each place gets a stable `place_key`, and the TRIP item accumulates `visited_place_keys` for the next crew call and server-side dedupe.

---

## Place

| Field | Type | Notes |
| --- | --- | --- |
| `place_id` | string | UUID assigned on save |
| `name` | string | Display name |
| `address` | string \| null | Street / area |
| `lat` / `lng` | float \| null | Optional; for maps later |
| `website_url` | string \| null | Official / booking link |
| `maps_url` | string \| null | Google Maps (or similar) link |
| `category` | enum | `museum` \| `food` \| `park` \| `transit` \| `lodging` \| `nightlife` \| `shopping` \| `nature` \| `other` |
| `reason_to_visit` | string | Why it fits this day |
| `details` | string | Practical description |
| `estimated_minutes` | int | Visit duration estimate (`> 0`) |
| `has_bathroom` | bool \| null | Public/visitor restroom available if known; `null` = unknown |
| `notes` | string \| null | Tips, tickets, hours |
| `order_in_day` | int | Sequence within the day |
| `place_key` | string | `normalize(name)\|normalize(address)` for cross-day dedupe |

## CityStop / CityRoute (before day plans)

If the user picks a country (or similar broad destination), we first decide which cities to visit and how many nights in each. That plan is a `CityRoute`: an ordered list of `CityStop`s. The user confirms it before we generate any day-by-day itineraries.

If the destination is already a single city, there is no route (`city_route` is null).

In DynamoDB this is stored as one `ROUTE` item on the trip.

### CityStop

| Field | Type | Notes |
| --- | --- | --- |
| `city` | string | City name |
| `country` | string | Country / region |
| `nights` | int | Nights to stay (`>= 0`) |
| `arrival_day_index` | int | First trip day index in this city |
| `departure_day_index` | int | Last trip day index in this city |
| `reason` | string | Why include this city in the window |
| `highlights` | string[] | Short teaser attractions (not full day plans yet) |

### CityRoute

| Field | Type | Notes |
| --- | --- | --- |
| `destination_type` | enum | `city` \| `country` \| `region` |
| `cities` | CityStop[] | Ordered route |
| `rationale` | string | Overall routing explanation |
| `total_nights` | int | Must fit `day_count` / overnight logic |
| `status` | enum | `proposed` \| `confirmed` |

## DayPlan

| Field | Type | Notes |
| --- | --- | --- |
| `day_index` | int | 1..14 |
| `date` | date | `YYYY-MM-DD` |
| `theme` | string | e.g. "Arrival & Left Bank" |
| `summary` | string | Short day narrative |
| `overnight_city` | string | Must match a confirmed route city when route exists |
| `places` | Place[] | Typically 3–6 stops |

## Trip (API aggregate)

| Field | Type | Notes |
| --- | --- | --- |
| `trip_id` | string | ULID/UUID |
| `user_id` | string | Cognito `sub` |
| `origin` / `destination` | string | Start / finish of the journey |
| `destination_type` | enum | `city` \| `country` \| `region` |
| `start_date` / `end_date` | date | Inclusive; max 14 days |
| `day_count` | int | Derived from dates |
| `next_day_index` | int | Next day to plan |
| `status` | enum | `drafting` \| `awaiting_city_confirm` \| `routing_confirmed` \| `planning` \| `complete` \| `failed` |
| `preferences` | string | Budget, pace, interests |
| `city_route` | CityRoute \| null | Set after propose/confirm; null for single-city trips |
| `visited_place_keys` | string[] | Keys already used (dedupe) |
| `prior_days_summary` | string | Compact context for the next crew call |
| `days` | DayPlan[] | Assembled from DAY items on read |

---

## DynamoDB single-table schema

### Why one table

We chose a **single-table** design instead of separate `Trips` / `Days` / `Routes` tables because our access patterns are hierarchical and user-scoped:

| Need | Single-table advantage |
| --- | --- |
| List my trips | One query on `pk = USER#{sub}` |
| Load a trip with route + all days | One query: `sk begins_with TRIP#{trip_id}` — meta, ROUTE, and DAY items share the same partition |
| Plan the next day | Read trip + prior days from that same query; write one DAY + update TRIP |
| Cost / ops | One table to provision, one IAM resource, on-demand billing with near-zero idle cost |

Multi-table would force the BFF to fan out (get trip from table A, days from table B, route from table C) and keep foreign keys in sync. For this app, entities are always owned by one user and almost always fetched as a trip bundle—so co-locating them under one partition is the natural DynamoDB fit.

We still distinguish entity types with `entity_type` and a structured `sk`, so the model stays clear without paying for extra tables.

### Why these keys

Keys are designed **from the access patterns**, not from a normalized ER diagram.

```text
pk = USER#{cognito_sub}
sk = TRIP#{trip_id}                 → trip metadata
sk = TRIP#{trip_id}#ROUTE           → city route (0 or 1)
sk = TRIP#{trip_id}#DAY#{nn}        → day nn (01..14)
```

**`pk = USER#{sub}`** — Every primary query is “for this signed-in user.” Cognito `sub` as partition key enforces isolation by construction: a user cannot query another user’s partition without knowing/forging their `sub` (and the BFF only uses the JWT’s `sub`).

**`sk` hierarchy with shared trip prefix** — Sort keys are sortable strings. Prefixing days and the route with `TRIP#{id}` means:

- `begins_with TRIP#` → all trip-related rows for the user (list screen filters to `entity_type = TRIP` only)
- `begins_with TRIP#{trip_id}` → that trip’s meta + route + days in one round trip
- exact `TRIP#{id}#DAY#03` → fetch or overwrite a single day

**Zero-padded `DAY#{nn}`** — Lexicographic order matches chronological order (`DAY#01` … `DAY#14`), so a query returns days already sorted.

**ROUTE as its own item** — City routing is confirmed *before* day planning and may be rewritten without touching day items. Keeping it separate avoids bloating trip meta and lets status (`proposed` / `confirmed`) live next to the route payload.

**Trip meta holds planning cursors** — `next_day_index`, `visited_place_keys`, and `prior_days_summary` live on the TRIP item so “plan next day” does not require scanning every DAY item to rebuild dedupe state (though we still load prior days when we want richer context).

### Why GSI1 (`TRIP#{trip_id}`)

Primary keys are user-first. Occasionally we only have a `trip_id` (deep link, AgentCore callback, support). GSI1 flips the lookup:

```text
gsi1pk = TRIP#{trip_id}
gsi1sk = USER#{sub} | ROUTE | DAY#{nn}
```

We still authorize with the JWT `sub` after the GSI fetch—GSI is convenience, not a security boundary.

### Why on-demand + optional TTL

Portfolio / demo traffic is bursty and often idle. **On-demand** avoids provisioned capacity sitting unused. Optional **`expires_at` TTL** on abandoned drafts keeps the table from accumulating junk trips without a cleanup job.

### Table definition

| Property | Value |
| --- | --- |
| Table name | `{project}-{env}-table` (e.g. `vacation-planner-dev-table`) |
| Billing | On-demand (`PAY_PER_REQUEST`) |
| Partition key | `pk` (String) |
| Sort key | `sk` (String) |
| GSI1 | `gsi1pk` + `gsi1sk` (lookup by `trip_id`) |
| TTL | `expires_at` (optional; abandoned drafts) |

### Access patterns

| Pattern | How | Why it matters |
| --- | --- | --- |
| List my trips | `pk = USER#{sub}`, `sk begins_with TRIP#`, filter `entity_type = TRIP` | Home screen; exclude DAY/ROUTE rows from the list |
| Get trip + route + days | `pk = USER#{sub}`, `sk begins_with TRIP#{trip_id}` | Timeline view and “plan next day” context in one query |
| Get one day | `pk = USER#{sub}`, `sk = TRIP#{trip_id}#DAY#{nn}` | Cheap refetch after planning a single day |
| Save a planned day | `PutItem` DAY; `UpdateItem` TRIP (`next_day_index`, `visited_place_keys`, `status`) | Append-only day growth; cursors stay on trip meta |
| Confirm city route | `PutItem`/`UpdateItem` ROUTE; update TRIP status | Gates day planning without rewriting days |
| Get trip by id only | GSI1: `gsi1pk = TRIP#{trip_id}` | Deep links / id-only callers; still check `sub` |

### Item shapes

**Trip metadata** (`entity_type = TRIP`)

```text
pk / sk:     USER#{sub}  /  TRIP#{trip_id}
gsi1pk/sk:   TRIP#{trip_id}  /  USER#{sub}
+ origin, destination, destination_type, start_date, end_date, day_count,
  next_day_index, status, preferences, visited_place_keys,
  prior_days_summary, created_at, updated_at, expires_at?
```

**City route** (`entity_type = ROUTE`) — one per trip when multi-city

```text
pk / sk:     USER#{sub}  /  TRIP#{trip_id}#ROUTE
gsi1pk/sk:   TRIP#{trip_id}  /  ROUTE
+ destination_type, cities[], rationale, total_nights, status,
  created_at, updated_at
```

**Day plan** (`entity_type = DAY`)

```text
pk / sk:     USER#{sub}  /  TRIP#{trip_id}#DAY#{nn}   # nn = 01..14
gsi1pk/sk:   TRIP#{trip_id}  /  DAY#{nn}
+ day_index, date, theme, summary, overnight_city, places[], created_at
  (each Place includes has_bathroom: bool | null)
```

### Example keys

```text
USER#abc-123  TRIP#01HXYZ...           → trip meta (10-day Japan)
USER#abc-123  TRIP#01HXYZ...#ROUTE     → Tokyo 4n → Kyoto 3n → Osaka 2n
USER#abc-123  TRIP#01HXYZ...#DAY#01    → day 1 in Tokyo
USER#abc-123  TRIP#01HXYZ...#DAY#02    → day 2 in Tokyo
...
```

### Deduping places

Dedupe is a product rule (“don’t send me to the same shrine on day 1 and day 4”) enforced in the BFF, not only in the LLM prompt:

1. Crew input includes `already_visited` (from `visited_place_keys` on the TRIP item).
2. After the model returns a `DayPlan`, drop places whose `place_key` already exists; retry once if fewer than 3 places remain.
3. Append new keys to `visited_place_keys` on the TRIP item.

Storing keys on the trip keeps the next planning call O(1) for the denylist instead of re-deriving keys from every prior day’s `places[]` (though we can still do that as a consistency check).

### What we deliberately skipped (for now)

| Alternative | Why not yet |
| --- | --- |
| Separate tables per entity | Extra joins and IAM for the same hierarchical reads |
| Place as its own item | No place-centric queries; would complicate day writes |
| OpenSearch / global place index | Out of scope for MVP; add if we need discovery across users |
| Storing full crew transcripts in DynamoDB | Large and noisy; use Phoenix locally / CloudWatch for runs |
