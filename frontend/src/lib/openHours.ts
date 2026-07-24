/** Parse Google weekdayDescriptions / semicolon blob into day rows. */

export type OpenHoursRow = {
  day: string;
  hours: string;
};

const DAY_ORDER = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

/**
 * Accepts:
 * - "Open 24 hours"
 * - newline- or "; "-separated "Monday: 11:00 AM – 3:00 PM" lines
 * - already-simple free text (returned as a single untitled row)
 */
export function parseOpenHours(raw: string | undefined | null): OpenHoursRow[] {
  const text = (raw || "").trim();
  if (!text) return [];

  const lower = text.toLowerCase();
  if (
    lower === "open 24 hours" ||
    lower === "open 24h" ||
    lower.includes("24 hours")
  ) {
    return [{ day: "Every day", hours: "Open 24 hours" }];
  }

  const parts = text
    .split(/\n+|;\s*/)
    .map((part) => part.trim())
    .filter(Boolean);

  const rows: OpenHoursRow[] = [];
  for (const part of parts) {
    const match = part.match(/^([A-Za-z]+)\s*:\s*(.+)$/);
    if (match) {
      rows.push({ day: match[1]!, hours: match[2]!.trim() });
      continue;
    }
  }

  if (rows.length === 0) {
    return [{ day: "Hours", hours: text }];
  }

  // Stable Mon→Sun order when we recognize weekday names.
  const rank = new Map(DAY_ORDER.map((d, i) => [d.toLowerCase(), i]));
  return [...rows].sort((a, b) => {
    const ra = rank.get(a.day.toLowerCase());
    const rb = rank.get(b.day.toLowerCase());
    if (ra == null && rb == null) return 0;
    if (ra == null) return 1;
    if (rb == null) return -1;
    return ra - rb;
  });
}
