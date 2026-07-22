type Props = {
  title?: string;
  message: string;
  /** Dismiss warning / keep city in draft */
  onKeep?: () => void;
  /** Remove the city that triggered the warning */
  onUndo?: () => void;
};

export function FeasibilityBanner({
  title = "This route may be tiring",
  message,
  onKeep,
  onUndo,
}: Props) {
  return (
    <div
      role="status"
      className="mt-4 rounded-xl border border-sand-deep bg-warn-soft/80 px-4 py-3 text-sm text-ink"
    >
      <p className="font-semibold text-warn">{title}</p>
      <p className="mt-1 text-ink-muted">{message}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          className="font-semibold text-teal underline-offset-2 hover:underline disabled:opacity-40"
          disabled={!onKeep}
          onClick={onKeep}
        >
          Keep city
        </button>
        <button
          type="button"
          className="font-semibold text-warn underline-offset-2 hover:underline disabled:opacity-40"
          disabled={!onUndo}
          onClick={onUndo}
        >
          Undo add
        </button>
      </div>
    </div>
  );
}
