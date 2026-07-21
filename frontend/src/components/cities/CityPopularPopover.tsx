export type CityHighlightCategory = {
  label: string;
  examples: string;
};

type Props = {
  city: string;
  categories: CityHighlightCategory[];
};

/** Compact hover/focus popover chrome — parent controls visibility. */
export function CityPopularPopover({ city, categories }: Props) {
  return (
    <div
      role="tooltip"
      className="absolute left-0 top-full z-20 mt-2 w-64 rounded-xl border border-line bg-surface p-3 shadow-lg"
    >
      <p className="font-display text-sm font-semibold text-ink">
        Popular in {city}
      </p>
      <ul className="mt-2 space-y-1.5">
        {categories.map((c) => (
          <li key={c.label} className="text-xs leading-snug text-ink-muted">
            <span className="font-semibold text-teal">{c.label}</span>
            {" · "}
            {c.examples}
          </li>
        ))}
      </ul>
    </div>
  );
}
