/** Dev-only crew mode preference (Vite DEV builds only). */

export type DevCrewMode = "fake" | "agentcore";

const STORAGE_KEY = "vp.devCrewMode";
export const DEV_CREW_MODE_CHANGE_EVENT = "vp-dev-crew-mode";

export function isDevCrewModeUiEnabled(): boolean {
  return import.meta.env.DEV === true;
}

export function getDevCrewMode(): DevCrewMode {
  if (!isDevCrewModeUiEnabled()) return "fake";
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "agentcore" ? "agentcore" : "fake";
  } catch {
    return "fake";
  }
}

export function setDevCrewMode(mode: DevCrewMode): void {
  if (!isDevCrewModeUiEnabled()) return;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore quota / private mode
  }
  window.dispatchEvent(new Event(DEV_CREW_MODE_CHANGE_EVENT));
}
