import { useEffect, useMemo, useState } from "react";
import {
  cityImageUrl,
  nextDefaultTravelImageUrl,
  travelImageKey,
} from "../../lib/travelAtmosphere";

type Props = {
  dayIndex: number;
  city: string;
  destination?: string;
};

function waitCopy(elapsedSec: number, city: string): string {
  if (elapsedSec < 25) {
    return `Gathering places for ${city} — usually about a minute.`;
  }
  if (elapsedSec < 70) {
    return `Still mapping ${city}. Worth the wait for a paced day.`;
  }
  return `Taking longer than usual for ${city} — hang tight.`;
}

/**
 * Compact in-timeline card while plan-next-day runs (day 2+).
 * Keeps existing days visible; city imagery anchors the wait.
 * On load error, walks the default travel set (never retries the same photo).
 */
export function InlineDayPlanningCard({
  dayIndex,
  city,
  destination = "",
}: Props) {
  const label = city.trim() || "your next stop";
  const preferredUrl = useMemo(
    () => cityImageUrl(label, destination).replace(/w=\d+/, "w=800"),
    [label, destination],
  );
  const [imageUrl, setImageUrl] = useState<string | null>(preferredUrl);
  const [failedUrls, setFailedUrls] = useState<string[]>([]);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    setImageUrl(preferredUrl);
    setFailedUrls([]);
  }, [preferredUrl]);

  useEffect(() => {
    const started = Date.now();
    const id = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [dayIndex, label]);

  return (
    <li className="relative" role="status" aria-live="polite" aria-busy="true">
      <span className="absolute -left-[1.9rem] flex h-7 w-7 items-center justify-center rounded-full bg-teal-soft text-xs font-semibold text-teal-deep">
        {dayIndex}
      </span>
      <div className="overflow-hidden rounded-xl border border-line/80 bg-surface">
        <div className="relative h-36 w-full bg-teal-deep sm:h-44">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt=""
              className="absolute inset-0 h-full w-full object-cover"
              onError={() => {
                if (!imageUrl) return;
                setFailedUrls((prev) => {
                  const key = travelImageKey(imageUrl);
                  if (prev.some((u) => travelImageKey(u) === key)) return prev;
                  const nextFailed = [...prev, imageUrl];
                  setImageUrl(nextDefaultTravelImageUrl(nextFailed, 800));
                  return nextFailed;
                });
              }}
            />
          ) : null}
          <div
            className="absolute inset-0 bg-gradient-to-t from-teal-deep/85 via-teal-deep/35 to-transparent"
            aria-hidden
          />
          <div className="propose-loading-shimmer absolute inset-x-0 bottom-0 h-1 overflow-hidden">
            <div className="propose-loading-shimmer-bar h-full w-1/3 bg-sand/80" />
          </div>
          <div className="relative flex h-full flex-col justify-end px-4 pb-4 pt-8">
            <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-sand/80">
              Planning day {dayIndex}
            </p>
            <p className="mt-1 font-display text-2xl font-semibold text-surface">
              {label}
            </p>
          </div>
        </div>
        <p className="px-4 py-3 text-sm text-ink-muted">
          {waitCopy(elapsedSec, label)}
        </p>
      </div>
    </li>
  );
}
