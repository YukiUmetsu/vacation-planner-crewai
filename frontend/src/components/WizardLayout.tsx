import { AuthBar } from "../auth/AuthBar";

export type WizardStep = "details" | "cities" | "days";

type Props = {
  step: WizardStep;
  children: React.ReactNode;
  /** When set, step labels are clickable (handy for demo navigation). */
  onStepChange?: (step: WizardStep) => void;
  demoBadge?: boolean;
  onOpenProfile?: () => void;
};

const STEPS: { id: WizardStep; label: string; n: number }[] = [
  { id: "details", label: "Details", n: 1 },
  { id: "cities", label: "Cities", n: 2 },
  { id: "days", label: "Days", n: 3 },
];

export function WizardLayout({
  step,
  children,
  onStepChange,
  demoBadge = false,
  onOpenProfile,
}: Props) {
  const activeIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4 py-8 sm:px-8 sm:py-10">
      <header className="mb-8 flex flex-col gap-6 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
              Vacation Planner
            </p>
            {demoBadge && (
              <span className="rounded-full bg-teal-soft px-2.5 py-0.5 text-xs font-semibold text-teal-deep">
                Demo data
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-ink-muted">
            Plan calmly — details, cities, then days.
            {onStepChange ? " Click a previous step to go back." : null}
          </p>
        </div>
        <div className="flex flex-col items-stretch gap-3 sm:items-end">
          <div className="flex flex-wrap items-center gap-2 self-start sm:self-end">
            <AuthBar />
            {onOpenProfile && (
              <button
                type="button"
                onClick={onOpenProfile}
                className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-teal hover:bg-teal-soft"
              >
                Profile
              </button>
            )}
          </div>
          <nav aria-label="Trip steps" className="flex items-center gap-2 sm:gap-4">
            {STEPS.map((s, i) => {
              const done = i < activeIndex;
              const active = s.id === step;
              const inner = (
                <>
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                      active
                        ? "bg-teal text-white"
                        : done
                          ? "bg-teal-soft text-teal-deep"
                          : "border border-line bg-surface text-ink-muted"
                    }`}
                  >
                    {done ? "✓" : s.n}
                  </span>
                  <span
                    className={`text-sm ${
                      active
                        ? "font-semibold underline decoration-2 underline-offset-4"
                        : ""
                    }`}
                  >
                    {s.label}
                  </span>
                </>
              );

              return (
                <div key={s.id} className="flex items-center gap-2 sm:gap-4">
                  {i > 0 && (
                    <span
                      className={`hidden h-px w-6 sm:block ${
                        done || active ? "bg-teal" : "bg-line"
                      }`}
                      aria-hidden
                    />
                  )}
                  {onStepChange ? (
                    <button
                      type="button"
                      onClick={() => onStepChange(s.id)}
                      className={`flex items-center gap-2 rounded-lg px-1 py-0.5 transition hover:opacity-80 ${
                        active
                          ? "text-teal-deep"
                          : done
                            ? "text-teal"
                            : "text-ink-muted"
                      }`}
                    >
                      {inner}
                    </button>
                  ) : (
                    <div
                      className={`flex items-center gap-2 ${
                        active
                          ? "text-teal-deep"
                          : done
                            ? "text-teal"
                            : "text-ink-muted"
                      }`}
                    >
                      {inner}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </div>
      </header>

      <div className="flex-1">{children}</div>
    </div>
  );
}
