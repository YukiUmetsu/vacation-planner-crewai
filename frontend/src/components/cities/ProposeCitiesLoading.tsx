import { useEffect, useMemo, useState } from "react";
import {
  defaultTravelScenes,
  pickQuestion,
  pickQuote,
  scenesForPlace,
  travelImageKey,
  type TravelScene,
} from "../../lib/travelAtmosphere";

const ROTATE_MS = 10_000;

type Props = {
  /** Trip destination (country / region) — used with ``place`` for scene seeding. */
  destination: string;
  /** Overnight / focus city when planning a day (preferred for imagery). */
  place?: string;
  /** Small uppercase label above the title. */
  eyebrow?: string;
  /** Hero title; defaults to ``place`` then ``destination``. */
  title?: string;
};

function scenesWithoutFailed(
  preferred: TravelScene[],
  failedKeys: ReadonlySet<string>,
): TravelScene[] {
  const okPreferred = preferred.filter(
    (s) => !failedKeys.has(travelImageKey(s.imageUrl)),
  );
  if (okPreferred.length > 0) return okPreferred;
  return defaultTravelScenes().filter(
    (s) => !failedKeys.has(travelImageKey(s.imageUrl)),
  );
}

/**
 * Full-bleed waiting experience while a crew plans cities or a day.
 * Rotates destination/city scenes, quotes, and traveler questions every 10s.
 * Failed image loads drop that URL and fall back to default travel scenes.
 */
export function TravelPlanningLoading({
  destination,
  place,
  eyebrow = "Sketching your route",
  title,
}: Props) {
  const focus = (place || destination).trim();
  const label = (title ?? focus).trim() || "your trip";
  const preferred = useMemo(
    () => scenesForPlace(place || "", destination || focus),
    [place, destination, focus],
  );
  const seed = focus || label;
  const [tick, setTick] = useState(0);
  /** Failed Unsplash pathnames (via travelImageKey), not full URLs. */
  const [failedKeys, setFailedKeys] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setFailedKeys(new Set());
    setTick(0);
  }, [place, destination, focus]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), ROTATE_MS);
    return () => window.clearInterval(id);
  }, [place, destination, focus]);

  const scenes = useMemo(
    () => scenesWithoutFailed(preferred, failedKeys),
    [preferred, failedKeys],
  );

  // Keep rotation in range when failed loads shrink the pool.
  const sceneCount = Math.max(scenes.length, 1);
  const scene = scenes.length > 0 ? scenes[tick % sceneCount]! : null;
  const quote = pickQuote(seed, tick);
  const question = pickQuestion(seed, tick);

  function markFailed(url: string) {
    const key = travelImageKey(url);
    if (!key) return;
    setFailedKeys((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }

  return (
    <div
      className="propose-loading relative -mx-6 -mt-2 overflow-hidden sm:-mx-8"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative min-h-[28rem] w-full bg-teal-deep sm:min-h-[32rem]">
        {scenes.map((s, i) => {
          const active = i === tick % scenes.length;
          return (
            <img
              key={s.imageUrl}
              src={s.imageUrl}
              alt=""
              className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 ease-out ${
                active ? "opacity-100" : "opacity-0"
              }`}
              onError={() => markFailed(s.imageUrl)}
            />
          );
        })}
        <div
          className="absolute inset-0 bg-gradient-to-t from-teal-deep/90 via-teal-deep/45 to-ink/20"
          aria-hidden
        />
        <div className="propose-loading-shimmer absolute inset-x-0 bottom-0 h-1 overflow-hidden">
          <div className="propose-loading-shimmer-bar h-full w-1/3 bg-sand/80" />
        </div>

        <div className="relative flex min-h-[28rem] flex-col justify-end px-10 pb-8 pt-16 sm:min-h-[32rem] sm:px-14 sm:pb-10">
          <p className="landing-fade-up text-xs font-semibold uppercase tracking-[0.2em] text-sand/80">
            {eyebrow}
          </p>
          <h2 className="landing-fade-up landing-delay-1 mt-2 font-display text-4xl font-semibold leading-tight text-surface sm:text-5xl">
            {label}
          </h2>
          <p
            key={`q-${tick}`}
            className="propose-copy-swap mt-6 max-w-xl font-display text-xl italic leading-snug text-sand sm:text-2xl"
          >
            “{quote}”
          </p>
          <p
            key={`ask-${tick}`}
            className="propose-copy-swap mt-5 max-w-lg text-sm leading-relaxed text-surface/90 sm:text-base"
          >
            <span className="font-semibold text-teal-soft">While you wait — </span>
            {question}
          </p>
          {scene ? (
            <p className="mt-6 text-xs text-sand/70">{scene.caption}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** @deprecated Prefer TravelPlanningLoading — kept as alias for cities propose. */
export function ProposeCitiesLoading(props: { destination: string }) {
  return <TravelPlanningLoading {...props} eyebrow="Sketching your route" />;
}
