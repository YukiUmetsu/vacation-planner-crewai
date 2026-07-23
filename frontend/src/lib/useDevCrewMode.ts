import { useEffect, useState } from "react";
import {
  DEV_CREW_MODE_CHANGE_EVENT,
  getDevCrewMode,
  isDevCrewModeUiEnabled,
  type DevCrewMode,
} from "./devCrewMode";

/** Live crew-mode preference in Vite DEV (null outside DEV). */
export function useDevCrewMode(): DevCrewMode | null {
  const enabled = isDevCrewModeUiEnabled();
  const [mode, setMode] = useState<DevCrewMode | null>(() =>
    enabled ? getDevCrewMode() : null,
  );

  useEffect(() => {
    if (!enabled) {
      setMode(null);
      return;
    }
    const sync = () => setMode(getDevCrewMode());
    sync();
    window.addEventListener(DEV_CREW_MODE_CHANGE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(DEV_CREW_MODE_CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, [enabled]);

  return mode;
}

export function crewModeLabel(mode: DevCrewMode): string {
  return mode === "agentcore" ? "AgentCore" : "Fake";
}
