import { useEffect, useMemo, useState } from "react";
import {
  pickQuestion,
  pickQuote,
  scenesForDestination,
} from "../../lib/travelAtmosphere";

const ROTATE_MS = 10_000;

type Props = {
  /** Used for scene / quote seeding (usually trip destination or overnight city). */
  destination: string;
  /** Small uppercase label above the title. */
  eyebrow?: string;
  /** Hero title; defaults to ``destination``. */
  title?: string;
};

/**
 * Full-bleed waiting experience while a crew plans cities or a day.
 * Rotates destination scenes, quotes, and traveler questions every 10s.
 */
export function TravelPlanningLoading({
  destination,
  eyebrow = "Sketching your route",
  title,
}: Props) {
  const label = (title ?? destination).trim() || "your trip";
  const seed = destination.trim() || label;
  const scenes = useMemo(() => scenesForDestination(seed), [seed]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), ROTATE_MS);
    return () => window.clearInterval(id);
  }, []);

  const scene = scenes[tick % scenes.length]!;
  const quote = pickQuote(seed, tick);
  const question = pickQuestion(seed, tick);

  return (
    <div
      className="propose-loading relative -mx-6 -mt-2 overflow-hidden sm:-mx-8"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative min-h-[28rem] w-full sm:min-h-[32rem]">
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
          <p className="mt-6 text-xs text-sand/70">{scene.caption}</p>
        </div>
      </div>
    </div>
  );
}

/** @deprecated Prefer TravelPlanningLoading — kept as alias for cities propose. */
export function ProposeCitiesLoading(props: { destination: string }) {
  return <TravelPlanningLoading {...props} eyebrow="Sketching your route" />;
}
