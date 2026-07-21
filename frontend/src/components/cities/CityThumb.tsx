type Props = {
  city: string;
  imageUrl?: string | null;
  className?: string;
};

/** Small square thumb; falls back to teal monogram. */
export function CityThumb({ city, imageUrl, className = "" }: Props) {
  const initial = city.trim().charAt(0).toUpperCase() || "?";

  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        className={`h-14 w-14 shrink-0 rounded-lg object-cover ${className}`}
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
