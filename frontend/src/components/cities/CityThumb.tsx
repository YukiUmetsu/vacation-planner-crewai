import { useEffect, useRef, useState } from "react";
import {
  nextDefaultTravelImageUrl,
  travelImageKey,
} from "../../lib/travelAtmosphere";
import { StableImage } from "../StableImage";

type Props = {
  city: string;
  imageUrl?: string | null;
  className?: string;
};

/**
 * Small square thumb.
 * On load error: walk default travel images, then teal monogram.
 */
export function CityThumb({ city, imageUrl, className = "" }: Props) {
  const [src, setSrc] = useState<string | null>(imageUrl?.trim() || null);
  const failedRef = useRef<string[]>([]);
  const initial = city.trim().charAt(0).toUpperCase() || "?";

  useEffect(() => {
    setSrc(imageUrl?.trim() || null);
    failedRef.current = [];
  }, [imageUrl, city]);

  if (src) {
    return (
      <StableImage
        src={src}
        alt=""
        className={`h-14 w-14 shrink-0 rounded-lg object-cover ${className}`}
        onDisplayError={() => {
          const prev = failedRef.current;
          const key = travelImageKey(src);
          if (prev.some((u) => travelImageKey(u) === key)) return;
          const nextFailed = [...prev, src];
          failedRef.current = nextFailed;
          setSrc(nextDefaultTravelImageUrl(nextFailed, 224));
        }}
      />
    );
  }

  return (
    <div
      className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-teal-soft font-display text-xl font-semibold text-teal-deep ${className}`}
      aria-hidden
    >
      {initial}
    </div>
  );
}
