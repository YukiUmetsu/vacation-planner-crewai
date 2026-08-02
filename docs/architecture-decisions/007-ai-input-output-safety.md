# ADR 007: AI input/output safety in the BFF

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** Project maintainers

## Context

Vacation Planner runs CrewAI crews on Bedrock AgentCore. The browser never calls AgentCore ([003](./003-bff-agentcore-runtime-only.md)), but traveler free text, prior AI summaries, and Serper/Amap tool results still enter prompts. Industry guidance (OWASP Agentic Top 10 / LLM01) treats prompt injection as unavoidable to fully eliminate; defenses should reduce success rate and **blast radius**.

## Decision

1. **BFF owns safety checks** via `SafetyGate` (`SAFETY_MODE=keyword|bedrock|off`):
   - **INPUT** (enforce): batch-check free text before GenAI spend (`check_texts` → one ApplyGuardrail call when Bedrock).
   - **OUTPUT** (`SAFETY_OUTPUT_MODE=observe|enforce`): batch-check AI prose before Dynamo persist; default **observe** (log `SAFETY_METRIC`, still save), then flip to **enforce** after soak.
2. **Fail modes:** Guardrail transport errors → INPUT fail-closed (`safety_check_unavailable`); OUTPUT fail-open so a Guardrail blip does not discard a finished plan.
3. **Link sanitize** on AI prose (strip non-allowlisted markdown/raw URLs) to reduce UI exfil.
4. **Tools stay narrow:** Serper + fixed-URL Amap only; scrub/cap Amap JSON in tool code; no Gateway/Browser/code tools. Prefer BFF gates over prompt-only mitigations (prompt edits require paid evals).
5. **AgentCore crew allowlist:** production invoke accepts BFF crews only; `day_plan_single` requires `ALLOW_EVAL_CREWS=1`.
6. **IAM-only AgentCore trust:** anyone with `InvokeAgentRuntime` bypasses Cognito — keep invoke on the BFF role only; `AUTH_MODE=dev` never in AWS.
7. **No security-driven crew prompt rewrites** in this ADR — quality prompts stay unchanged so offline/live eval baselines remain valid.

## Consequences

- Extra ~1–2 Guardrail RTTs per GenAI operation when `SAFETY_MODE=bedrock` (batched, not N+1).
- Keyword denylist remains a local/dev backup (~12 multi-word jailbreak phrases) — not a production substitute for Bedrock.
- Quality retries may still spend Bedrock/Serper after one GenAI quota tick ([006](./006-admin-limits-genai-caps.md)); agent `max_iter` caps tool loops.
- Deferred: AgentCore Gateway, plan-then-execute dual-LLM CFI, forking Serper.

## Follow-ups

- [ ] Soak `SAFETY_OUTPUT_MODE=observe` in AWS, then set `enforce`
- [ ] Optional: stricter GenAI retry budget if cost abuse appears in metrics
