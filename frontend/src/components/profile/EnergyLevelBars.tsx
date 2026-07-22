import type { KeyboardEvent } from "react";
import {
  ENERGY_LEVEL_LABELS,
  ENERGY_LEVELS,
  type EnergyLevel,
  clampEnergyLevel,
} from "../../lib/energyLevel";

type Props = {
  value: EnergyLevel;
  onChange: (level: EnergyLevel) => void;
  id?: string;
};

/** Signal-bar control for traveler energy (1–5) with radiogroup keyboard support. */
export function EnergyLevelBars({ value, onChange, id = "energy-level" }: Props) {
  const level = clampEnergyLevel(value);

  function select(next: EnergyLevel) {
    onChange(next);
  }

  function onRadioKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    current: EnergyLevel,
  ) {
    const index = ENERGY_LEVELS.indexOf(current);
    let nextIndex = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      nextIndex = Math.min(ENERGY_LEVELS.length - 1, index + 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      nextIndex = Math.max(0, index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      nextIndex = 0;
    } else if (event.key === "End") {
      event.preventDefault();
      nextIndex = ENERGY_LEVELS.length - 1;
    } else {
      return;
    }
    const next = ENERGY_LEVELS[nextIndex]!;
    select(next);
    queueMicrotask(() => {
      document.getElementById(`${id}-radio-${next}`)?.focus();
    });
  }

  return (
    <div>
      <div
        className="flex items-end gap-1.5"
        role="radiogroup"
        aria-labelledby={`${id}-label`}
      >
        {ENERGY_LEVELS.map((bar) => {
          const filled = bar <= level;
          const selected = bar === level;
          return (
            <button
              key={bar}
              id={`${id}-radio-${bar}`}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={selected ? 0 : -1}
              aria-label={`Energy level ${bar}: ${ENERGY_LEVEL_LABELS[bar]}`}
              title={ENERGY_LEVEL_LABELS[bar]}
              onClick={() => select(bar)}
              onKeyDown={(event) => onRadioKeyDown(event, bar)}
              className="group flex flex-col items-center gap-1 rounded-md p-1 outline-none focus-visible:ring-2 focus-visible:ring-teal"
            >
              <span
                aria-hidden
                className={`w-3 rounded-sm transition ${barFillClass(bar, filled)} ${
                  selected ? "ring-2 ring-offset-1 ring-teal-deep" : ""
                }`}
                style={{ height: `${10 + bar * 6}px` }}
              />
              <span
                className={`text-[10px] font-semibold tabular-nums ${
                  filled ? "text-ink" : "text-ink-muted"
                }`}
              >
                {bar}
              </span>
            </button>
          );
        })}
      </div>
      <p id={`${id}-label`} className="mt-2 text-sm text-ink-muted">
        <span className="font-semibold text-ink">Level {level}</span>
        {" — "}
        {ENERGY_LEVEL_LABELS[level]}
      </p>
    </div>
  );
}

function barFillClass(bar: EnergyLevel, filled: boolean): string {
  if (!filled) return "bg-line";
  switch (bar) {
    case 1:
      return "bg-warn";
    case 2:
      return "bg-[#d97706]";
    case 3:
      return "bg-teal";
    case 4:
      return "bg-teal-deep";
    case 5:
      return "bg-[#047857]";
    default:
      return "bg-teal";
  }
}
