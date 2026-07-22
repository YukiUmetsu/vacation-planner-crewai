type Props = {
  hydrating: boolean;
  actionError: string | null;
};

/** Loading / error strip above wizard steps. */
export function TripStatusBanner({ hydrating, actionError }: Props) {
  if (!hydrating && !actionError) return null;

  return (
    <div className="mb-4 space-y-1 text-sm">
      {hydrating && (
        <p className="text-ink-muted" role="status">
          Loading trip…
        </p>
      )}
      {actionError && (
        <p className="text-warn" role="alert">
          {actionError}
        </p>
      )}
    </div>
  );
}
