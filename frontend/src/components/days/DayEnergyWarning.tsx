import { formatDuration } from "../../demo/dayTimes";
import type { DayEnergyLoad } from "../../lib/energyLevel";

type Props = {
  load: DayEnergyLoad;
};

/** Inline warning when a day's total time exceeds the traveler's energy comfort. */
export function DayEnergyWarning({ load }: Props) {
  if (load.severity === "ok" || !load.message) return null;

  const isOver = load.severity === "overloaded";

  return (
    <div
      role="status"
      className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
        isOver
          ? "border-warn/40 bg-warn-soft text-warn"
          : "border-amber-200 bg-amber-50 text-amber-900"
      }`}
    >
      <p className="font-semibold">
        {isOver ? "Energy load warning" : "Energy load caution"}
      </p>
      <p className="mt-0.5 leading-snug opacity-90">{load.message}</p>
      <p className="mt-1 text-xs opacity-80">
        Planned {formatDuration(load.totalMinutes)} · comfort about{" "}
        {formatDuration(load.comfortMaxMinutes)} at level {load.level}
      </p>
    </div>
  );
}
