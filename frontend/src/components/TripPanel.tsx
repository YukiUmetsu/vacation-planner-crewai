import { useQuery } from "@tanstack/react-query";
import { getTrip } from "../api/trips";
import { TripGist } from "./TripGist";

type Props = {
  tripId: string;
  /** LEARNING: pass setters when you add wizard step state in App */
  onContinueToCities?: () => void;
  onContinueToDays?: () => void;
};

export function TripPanel({
  tripId,
  onContinueToCities,
  onContinueToDays,
}: Props) {
  const tripQuery = useQuery({
    queryKey: ["trip", tripId],
    queryFn: () => getTrip(tripId),
  });

  if (tripQuery.isPending) {
    return (
      <p className="text-sm text-ink-muted" role="status">
        Loading trip…
      </p>
    );
  }

  if (tripQuery.isError) {
    return (
      <p className="text-sm text-warn" role="alert">
        Load failed: {(tripQuery.error as Error).message}
      </p>
    );
  }

  const { trip, route, days } = tripQuery.data;

  return (
    <TripGist
      trip={trip}
      route={route}
      days={days}
      onContinueToCities={onContinueToCities}
      onContinueToDays={onContinueToDays}
    />
  );
}
