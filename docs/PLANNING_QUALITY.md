# Planning quality, safety, and evals

Canonical product rules for how we judge a day’s plan. Package READMEs hold implementation detail; this doc is the shared contract.

## Doc map (safety / guardrails / evals)

There is **no** older standalone safety-only markdown. Use:

| Topic | Where |
| --- | --- |
| **Traveler energy ↔ day load** | This file (canonical thresholds) |
| **Input safety (prompt injection / harmful prefs)** | [`backend/README.md`](../backend/README.md) (`SAFETY_MODE`), [`backend/src/services/bedrock_safety.py`](../backend/src/services/bedrock_safety.py) |
| **Bedrock Guardrail policies + IAM** | [`infra/README.md`](../infra/README.md) (Guardrails section), [`infra/guardrails/`](../infra/guardrails/) |
| **Offline crew evals** | [`agent/evals/README.md`](../agent/evals/README.md) |
| **AgentCore trust boundary** | [ADR 003](./architecture-decisions/003-bff-agentcore-runtime-only.md) |

Future work (not enforced yet): permanently closed venues, closed-on-weekday checks, server-side profile prefs, crew reviewer pass — see “Roadmap” below.

---

## Energy level → warning thresholds

Traveler **energy level** is an integer **1–5** (signal bars in the profile UI).

**What we measure:** total planned minutes for one day =

- sum of place `estimated_minutes` (activity), plus  
- sum of `travel_minutes_from_previous` between stops (travel).

Code: `frontend/src/lib/energyLevel.ts` (`MAX_COMFORTABLE_TOTAL_MINUTES`) and `frontend/src/demo/dayTimes.ts`.

These values are **when the UI starts warning** (`caution`), not “ideal day length.” A typical moderate sightseeing day can sit well under the level-3 line.

### Warning thresholds (canonical)

| Energy | Meaning (short) | Warn after (activity + travel) | Minutes |
| --- | --- | --- | ---: |
| **1** | Very low — limited mobility / long rests | **4.5 hours** | 270 |
| **2** | Low — short days, frequent breaks | **6.5 hours** | 390 |
| **3** | Moderate — average adult day (default) | **8.5 hours** | 510 |
| **4** | High — long active days | **12 hours** | 720 |
| **5** | Very high — packed itineraries OK | **14 hours** | 840 |

These are **soft** UX thresholds today (banner on the Days step). They are **not** yet enforced in the day crew or backend. When a reviewer / scorer is added, use the same minute table.

### Severity bands

Let `ratio = totalMinutes / comfortMaxMinutes` (where comfort max = warning threshold above).

| Band | Condition | UI |
| --- | --- | --- |
| `ok` | `ratio ≤ 1` | No warning |
| `caution` | `1 < ratio ≤ 1.2` | Soft “a bit packed” message |
| `overloaded` | `ratio > 1.2` | Stronger “too full” message |

Example: energy **3** → warn after **510** min (8.5h). Day with **540** min → caution. Day with **620** min → overloaded (&gt;1.2× ≈ 612 min).

### Using the mapping elsewhere

- **Frontend:** `assessDayEnergyLoad(energyLevel, totalMinutes)`.
- **Crew / reviewer (planned):** pass `energy_level` and `max_comfortable_minutes` in planning context; reject or revise if overloaded.
- **Offline evals (planned):** optional `expected.max_total_minutes` or derive from fixture `energy_level`.

Keep this table and `MAX_COMFORTABLE_TOTAL_MINUTES` in sync. If you change one, change both.

---

## Related hard checks (today)

| Check | Layer |
| --- | --- |
| Dedupe places across days (`place_key`) | Backend `dedupe_places` + crew `already_visited` prompt |
| Place count 3–6 / schema | Agent `DayPlan` Pydantic + eval scorers |
| Suggest one more place | `suggest_place` crew + `validate_suggested_place` + eval `score_suggest_place` |
| User preference / destination text safety | Backend safety gate (keyword or ApplyGuardrail) |

---

## Roadmap (quality)

1. [x] Persist profile (prefs, energy, interests) in DynamoDB; inject into `plan-next-day`.
2. [x] Enforce energy caps + closed / weekday-closed checks in offline scorers **and** API post-crew `place_quality` filter; reviewer crew task (brief-only swaps, no new research tools).
3. [x] Suggest one more place: `suggest_place` crew + `POST /trips/{id}/days/{n}/suggest-place` with `validate_suggested_place` (day cap 6, closed/visited, energy vs remaining) + offline scorer.
4. Venue open status via Places API when Serper is not enough (tool-assisted discovery remains soft).
