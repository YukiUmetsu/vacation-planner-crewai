import type { UserProfile } from "../components/profile/ProfilePage";

export const DEMO_PROFILE: UserProfile = {
  displayName: "Yuki",
  preferences:
    "Medium pace, great local food, prefer trains over buses, skip extreme hikes.",
  interests: ["Food", "Culture", "Trains"],
  visitedPlaces: [
    { name: "Senso-ji", city: "Tokyo" },
    { name: "Fushimi Inari", city: "Kyoto" },
  ],
};
