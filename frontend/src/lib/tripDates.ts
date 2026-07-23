/** Keep trip end_date on or after start_date (YYYY-MM-DD lexicographic compare). */

export const MAX_TRIP_DAYS = 14;

/** Inclusive calendar days: Aug 1–Aug 14 → 14 (not end−start). */
export function inclusiveDayCount(startDate: string, endDate: string): number {
  if (!startDate || !endDate) return 0;
  const start = parseIsoDate(startDate);
  const end = parseIsoDate(endDate);
  if (!start || !end || end < start) return 0;
  return diffUtcDays(start, end) + 1;
}

/** Latest end date allowed for a max-length trip starting on ``startDate``. */
export function maxEndDateForStart(startDate: string, maxDays = MAX_TRIP_DAYS): string {
  const start = parseIsoDate(startDate);
  if (!start) return startDate;
  return formatIsoDate(addUtcDays(start, maxDays - 1));
}

export function clampEndDateToStart(startDate: string, endDate: string): string {
  if (!startDate) return endDate;
  if (!endDate || endDate < startDate) return startDate;
  const maxEnd = maxEndDateForStart(startDate);
  if (endDate > maxEnd) return maxEnd;
  return endDate;
}

export function withStartDateChange<T extends { start_date: string; end_date: string }>(
  form: T,
  startDate: string,
): T {
  return {
    ...form,
    start_date: startDate,
    end_date: clampEndDateToStart(startDate, form.end_date),
  };
}

export function withEndDateChange<T extends { start_date: string; end_date: string }>(
  form: T,
  endDate: string,
): T {
  return {
    ...form,
    end_date: clampEndDateToStart(form.start_date, endDate),
  };
}

function parseIsoDate(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (
    dt.getUTCFullYear() !== y ||
    dt.getUTCMonth() !== mo - 1 ||
    dt.getUTCDate() !== d
  ) {
    return null;
  }
  return dt;
}

function formatIsoDate(dt: Date): string {
  const y = dt.getUTCFullYear();
  const mo = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const d = String(dt.getUTCDate()).padStart(2, "0");
  return `${y}-${mo}-${d}`;
}

function addUtcDays(dt: Date, days: number): Date {
  const next = new Date(dt.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function diffUtcDays(start: Date, end: Date): number {
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}
