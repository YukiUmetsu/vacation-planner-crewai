export type DestinationType = "city" | "country" | "region";

export type CreateTripInput = {
    origin: string;
    destination: string;
    destination_type: DestinationType;
    start_date: string; // YYYY-MM-DD
    end_date: string; // YYYY-MM-DD
    preferences?: string;
};

export type Trip = {
    trip_id: string;
    origin: string;
    destination: string;
    destination_type: DestinationType;
    start_date: string; // YYYY-MM-DD
    end_date: string; // YYYY-MM-DD
    day_count: number;
    preferences?: string;
    status: string;
    next_day_index?: number;
}

export type CityStop = {
    city: string;
    country?: string;
    nights: number;
    arrival_day_index: number;
    departure_day_index: number;
    reason?: string;
    highlights?: string[];
    /** Frontend-only id so undo can target one row when city names collide. */
    client_id?: string;
};

export type Route = {
    destination_type: DestinationType;
    cities: CityStop[];
    rationale?: string;
    total_nights: number;
    status: "proposed" | "confirmed" | string;
}

export type PlaceWatchOut = {
  label: string;
  detail: string;
};

export type Place = {
  name: string;
  address?: string;
  category?: string;
  reason_to_visit?: string;
  details?: string;
  estimated_minutes?: number;
  has_bathroom?: boolean | null;
  notes?: string | null;
  order_in_day?: number;
  place_key: string;
  /** Rich detail (demo / later crew enrichment) */
  cost?: string;
  open_hours?: string;
  operational_status?: "open" | "closed" | "unknown";
  /** Monday=0 … Sunday=6 */
  closed_weekdays?: number[];
  main_attraction?: string;
  map_url?: string;
  map_embed_query?: string;
  why_suggested?: string;
  watch_outs?: PlaceWatchOut[];
  /** Minutes to reach this place from the previous stop in the day (0 for first). */
  travel_minutes_from_previous?: number;
};


export type DayPlan = {
    day_index: number;
    date: string; // YYYY-MM-DD from the API (JSON), not a Date object
    theme: string;
    summary?: string;
    overnight_city: string;
    places: Place[];
};

export type TripBundle = {
    trip: Trip;
    route: Route | null;
    days: DayPlan[];
}