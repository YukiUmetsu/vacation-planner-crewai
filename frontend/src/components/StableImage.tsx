/**
 * Hold the previous good frame while a new src preloads.
 * Never paint a URL until preload succeeds — avoids broken-image flashes.
 */
import { useEffect, useRef, useState, type ImgHTMLAttributes } from "react";

type Props = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "onLoad" | "onError"> & {
  src: string;
  /** Called when preload or the committed image fails. */
  onDisplayError?: () => void;
};

export function StableImage({ src, onDisplayError, alt = "", className, ...rest }: Props) {
  const [displaySrc, setDisplaySrc] = useState<string | null>(null);
  const [pendingSrc, setPendingSrc] = useState<string | null>(null);
  const displaySrcRef = useRef<string | null>(null);
  const onDisplayErrorRef = useRef(onDisplayError);
  onDisplayErrorRef.current = onDisplayError;

  useEffect(() => {
    displaySrcRef.current = displaySrc;
  }, [displaySrc]);

  useEffect(() => {
    const next = src.trim();
    if (!next) {
      setDisplaySrc(null);
      setPendingSrc(null);
      return;
    }
    if (next === displaySrcRef.current) {
      setPendingSrc(null);
      return;
    }

    let cancelled = false;
    const img = new Image();
    img.referrerPolicy =
      typeof rest.referrerPolicy === "string" ? rest.referrerPolicy : "no-referrer";
    img.onload = () => {
      if (cancelled) return;
      setDisplaySrc(next);
      setPendingSrc(null);
    };
    img.onerror = () => {
      if (cancelled) return;
      setPendingSrc(null);
      // Drop the previous frame so a failed identity change does not keep
      // the old photo under new labels (parent shows gradient underneath).
      setDisplaySrc(null);
      onDisplayErrorRef.current?.();
    };
    setPendingSrc(next);
    img.src = next;
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- preload only on src
  }, [src]);

  if (!displaySrc) return null;

  return (
    <img
      {...rest}
      src={displaySrc}
      alt={alt}
      className={className}
      data-pending={pendingSrc ? "true" : undefined}
      onError={() => {
        setDisplaySrc(null);
        onDisplayErrorRef.current?.();
      }}
    />
  );
}
