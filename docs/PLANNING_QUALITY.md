# Planning quality, safety, and evals

Canonical product rules for how we judge a day’s plan. Package READMEs hold implementation detail; this doc is the shared contract.

## Doc map (safety / guardrails / evals)

| Topic | Where |
| --- | --- |
| **Traveler energy ↔ day load** | This file (canonical thresholds) |
| **Input safety (prompt injection / harmful prefs)** | [`backend/README.md`](../backend/README.md) (`SAFETY_MODE`), [`backend/src/services/bedrock_safety.py`](../backend/src/services/bedrock_safety.py) |
| **Bedrock Guardrail policies + IAM** | [`infra/README.md`](../infra/README.md) (Guardrails section), [`infra/guardrails/`](../infra/guardrails/) |
| **Offline crew evals** | [`agent/evals/README.md`](../agent/evals/README.md) |
| **AgentCore trust boundary** | [ADR 003](./architecture-decisions/003-bff-agentcore-runtime-only.md) |

---

## Energy level → warning thresholds

Traveler **energy level** is an integer **1–5** (signal bars in the profile UI).

**What we measure:** total planned minutes for one day =

- sum of place `estimated_minutes` (activity), plus  
- sum of `travel_minutes_from_previous` between stops (travel).

Canonical minute table (keep in sync):

- Frontend: `frontend/src/lib/energyLevel.ts` (`MAX_COMFORTABLE_TOTAL_MINUTES`)
- Backend: `backend/src/services/energy.py`
- Offline scorers: `agent/evals/scorers.py`

### Warning thresholds (canonical)

| Energy | Meaning (short) | Warn after (activity + travel) | Minutes |
| --- | --- | --- | ---: |
| **1** | Very low — limited mobility / long rests | **4.5 hours** | 270 |
| **2** | Low — short days, frequent breaks | **6.5 hours** | 390 |
| **3** | Moderate — average adult day (default) | **8.5 hours** | 510 |
| **4** | High — long active days | **12 hours** | 720 |
| **5** | Very high — packed itineraries OK | **14 hours** | 840 |

### Soft vs hard enforcement

| Layer | Behavior |
| --- | --- |
| **Frontend** | Soft banner via `assessDayEnergyLoad` (`ok` / `caution` / `overloaded`) |
| **Crew prompts** | `energy_level` + `max_comfortable_minutes` / `remaining_minutes` in day_plan + suggest_place |
| **API hard gate** | `place_quality.filter_quality_places` (plan-next-day) and `validate_suggested_place` (suggest-place) reject over-budget days |
| **Offline evals** | Scorers fail when day/suggestion exceeds the threshold |

### Severity bands (UI)

Let `ratio = totalMinutes / comfortMaxMinutes`.

| Band | Condition | UI |
| --- | --- | --- |
| `ok` | `ratio ≤ 1` | No warning |
| `caution` | `1 < ratio ≤ 1.2` | Soft “a bit packed” message |
| `overloaded` | `ratio > 1.2` | Stronger “too full” message |

Example: energy **3** → warn after **510** min. Day with **540** min → caution. Day with **620** min → overloaded.

---

## Related hard checks (today)

| Check | Layer |
| --- | --- |
| Dedupe places across days (`place_key`) | Backend `dedupe_places` + crew `already_visited` prompt |
| Place count 3–6 / schema | Agent `DayPlan` Pydantic + eval scorers |
| Permanently closed / weekday-closed | Crew reviewer + `place_quality` + scorers |
| Energy budget | Crew prompts + `place_quality` / `validate_suggested_place` + scorers |
| Suggest one more place | `suggest_place` crew + `validate_suggested_place` + `score_suggest_place` |
| Profile prefs / energy / interests | DynamoDB `PROFILE` injected into plan-next-day + suggest-place |
| User preference / destination text safety | Backend safety gate (keyword or ApplyGuardrail) |

---

## Roadmap (quality)

1. [x] Persist profile (prefs, energy, interests) in DynamoDB; inject into `plan-next-day`.
2. [x] Enforce energy caps + closed / weekday-closed checks in offline scorers **and** API post-crew `place_quality` filter; reviewer crew task (brief-only swaps, no new research tools).
3. [x] Suggest one more place: `suggest_place` crew + `POST /trips/{id}/days/{n}/suggest-place` with `validate_suggested_place` + offline scorer.
4. Venue open status via Places API when Serper is not enough (tool-assisted discovery remains soft).
