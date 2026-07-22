import {
  ProfilePage,
  type UserProfile,
} from "./profile/ProfilePage";

type Props = {
  demoMode: boolean;
  profile: UserProfile;
  onChange: (next: UserProfile) => void;
  onBack: () => void;
};

/** Full-page profile view (outside the trip wizard rail). */
export function ProfileScreen({
  demoMode,
  profile,
  onChange,
  onBack,
}: Props) {
  return (
    <div className="mx-auto min-h-dvh max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
      <p className="mb-6 font-display text-3xl font-semibold text-ink">
        Vacation Planner
        {demoMode && (
          <span className="ml-3 align-middle rounded-full bg-teal-soft px-2.5 py-0.5 text-xs font-semibold text-teal-deep">
            Demo data
          </span>
        )}
      </p>
      <ProfilePage profile={profile} onChange={onChange} onBack={onBack} />
    </div>
  );
}
