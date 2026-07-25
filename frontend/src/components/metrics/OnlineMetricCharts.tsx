import type { CountRow, DayBucket } from "../../lib/onlineMetricsSummary";

type StatCardProps = {
  label: string;
  value: string;
  hint?: string;
};

export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="rounded border border-line bg-surface/80 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      <p className="mt-1 font-display text-2xl font-semibold tabular-nums text-ink">
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  );
}

type HorizontalBarsProps = {
  title: string;
  rows: CountRow[];
  emptyLabel: string;
};

export function HorizontalBars({ title, rows, emptyLabel }: HorizontalBarsProps) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="rounded border border-line bg-surface/80 p-4">
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">{emptyLabel}</p>
      ) : (
        <ul className="mt-3 space-y-2" aria-label={title}>
          {rows.map((row) => (
            <li key={row.label} className="grid grid-cols-[7rem_1fr_2rem] items-center gap-2 text-sm">
              <span className="truncate font-mono text-xs text-ink-muted" title={row.label}>
                {row.label}
              </span>
              <div
                className="h-2 overflow-hidden rounded bg-line"
                role="presentation"
              >
                <div
                  className="h-full rounded bg-teal"
                  style={{ width: `${(row.count / max) * 100}%` }}
                />
              </div>
              <span className="tabular-nums text-ink">{row.count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type StackedDayBarsProps = {
  title: string;
  buckets: DayBucket[];
  emptyLabel: string;
};

export function StackedDayBars({
  title,
  buckets,
  emptyLabel,
}: StackedDayBarsProps) {
  const max = Math.max(
    1,
    ...buckets.map((b) => b.pass + b.fail + b.retry),
  );
  return (
    <div className="rounded border border-line bg-surface/80 p-4">
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      <p className="mt-1 text-xs text-ink-muted">
        <span className="mr-3 inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-teal" /> pass
        </span>
        <span className="mr-3 inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-warn" /> fail
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-sand-deep" /> retry
        </span>
      </p>
      {buckets.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">{emptyLabel}</p>
      ) : (
        <ul className="mt-4 flex h-36 items-end gap-1.5" aria-label={title}>
          {buckets.map((b) => {
            const total = b.pass + b.fail + b.retry;
            const barPx = total ? Math.max(8, Math.round((total / max) * 128)) : 2;
            const passPx = total ? Math.round((b.pass / total) * barPx) : 0;
            const failPx = total ? Math.round((b.fail / total) * barPx) : 0;
            const retryPx = Math.max(0, barPx - passPx - failPx);
            return (
              <li
                key={b.day}
                className="flex min-w-0 flex-1 flex-col items-center gap-1"
                title={`${b.day}: ${b.pass} pass, ${b.fail} fail, ${b.retry} retry`}
              >
                <div
                  className="flex w-full max-w-[2rem] flex-col justify-end overflow-hidden rounded-sm bg-line/40"
                  style={{ height: `${barPx}px` }}
                >
                  {retryPx > 0 ? (
                    <div
                      className="w-full shrink-0 bg-sand-deep"
                      style={{ height: `${retryPx}px` }}
                    />
                  ) : null}
                  {failPx > 0 ? (
                    <div
                      className="w-full shrink-0 bg-warn"
                      style={{ height: `${failPx}px` }}
                    />
                  ) : null}
                  {passPx > 0 ? (
                    <div
                      className="w-full shrink-0 bg-teal"
                      style={{ height: `${passPx}px` }}
                    />
                  ) : null}
                </div>
                <span className="w-full truncate text-center text-[0.65rem] text-ink-muted">
                  {b.day.slice(5)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
