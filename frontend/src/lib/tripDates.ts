/** Keep trip end_date on or after start_date (YYYY-MM-DD lexicographic compare). */

export function clampEndDateToStart(startDate: string, endDate: string): string {
  if (!startDate) return endDate;
  if (!endDate || endDate < startDate) return startDate;
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
