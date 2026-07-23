import { setDevCrewMode } from "../lib/devCrewMode";
import { crewModeLabel, useDevCrewMode } from "../lib/useDevCrewMode";

/**
 * Fixed bottom control to toggle Fake vs AgentCore crews (shows current mode).
 * Rendered only in Vite DEV builds — stripped from production.
 */
export function DevCrewModeSwitch() {
  const mode = useDevCrewMode();
  if (mode == null) return null;

  const agentcore = mode === "agentcore";
  const label = crewModeLabel(mode);

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center p-3 sm:justify-end sm:p-4"
      data-testid="dev-crew-mode-switch"
      role="status"
      aria-live="polite"
    >
      <div className="pointer-events-auto flex max-w-full flex-col gap-1.5 rounded-xl border border-amber-700/40 bg-amber-50/95 px-3 py-2 shadow-md backdrop-blur-sm sm:flex-row sm:items-center sm:gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-900/80">
            Dev · switch crews
          </p>
          <p className="text-xs font-semibold text-amber-950">
            Currently:{" "}
            <span data-testid="dev-crew-mode-current">{label}</span>
          </p>
        </div>
        <div
          role="group"
          aria-label="Crew backend"
          className="flex overflow-hidden rounded-lg border border-amber-800/20"
        >
          <button
            type="button"
            aria-pressed={!agentcore}
            onClick={() => setDevCrewMode("fake")}
            className={`px-3 py-1.5 text-xs font-semibold transition ${
              !agentcore
                ? "bg-amber-900 text-amber-50"
                : "bg-transparent text-amber-950/70 hover:bg-amber-100"
            }`}
          >
            Fake
          </button>
          <button
            type="button"
            aria-pressed={agentcore}
            onClick={() => setDevCrewMode("agentcore")}
            className={`px-3 py-1.5 text-xs font-semibold transition ${
              agentcore
                ? "bg-amber-900 text-amber-50"
                : "bg-transparent text-amber-950/70 hover:bg-amber-100"
            }`}
          >
            AgentCore
          </button>
        </div>
      </div>
    </div>
  );
}
