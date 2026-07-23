import { logout } from "./oauth";
import { isCognitoConfigured } from "./config";
import { isSignedIn } from "./session";
import { useEffect, useState } from "react";

/**
 * Signed-in control (Sign out). Provider pick lives on the landing page.
 */
export function AuthBar() {
  const [signedIn, setSignedIn] = useState(false);
  const configured = isCognitoConfigured();

  useEffect(() => {
    setSignedIn(isSignedIn());
  }, []);

  if (!configured || !signedIn) {
    return null;
  }

  return (
    <button
      type="button"
      className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink hover:bg-teal-soft"
      onClick={() => logout({ federated: true })}
    >
      Sign out
    </button>
  );
}
