/** Cognito Hosted UI env — filled from Terraform outputs at build time. */

export type CognitoIdentityProvider = "COGNITO" | "Google" | "Facebook";

export type CognitoConfig = {
  domain: string;
  clientId: string;
  redirectUri: string;
  logoutUri: string;
  scopes: string;
  /** Enabled IdPs from Terraform (always includes COGNITO when configured). */
  identityProviders: CognitoIdentityProvider[];
};

const KNOWN_PROVIDERS = new Set<string>(["COGNITO", "Google", "Facebook"]);

function read(name: string): string {
  const raw = import.meta.env[name];
  return typeof raw === "string" ? raw.trim() : "";
}

function parseIdentityProviders(raw: string): CognitoIdentityProvider[] {
  const parts = raw
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean)
    .filter((p): p is CognitoIdentityProvider => KNOWN_PROVIDERS.has(p));
  if (parts.length === 0) {
    return ["COGNITO"];
  }
  return [...new Set(parts)];
}

/** True when all Cognito Vite env vars are set (deploy / local Hosted UI testing). */
export function isCognitoConfigured(): boolean {
  return Boolean(
    read("VITE_COGNITO_DOMAIN") &&
      read("VITE_COGNITO_CLIENT_ID") &&
      read("VITE_COGNITO_REDIRECT_URI"),
  );
}

export function getCognitoConfig(): CognitoConfig {
  if (!isCognitoConfigured()) {
    throw new Error(
      "Cognito env missing. Set VITE_COGNITO_DOMAIN, VITE_COGNITO_CLIENT_ID, VITE_COGNITO_REDIRECT_URI (see docs/ENVIRONMENT.md).",
    );
  }
  return {
    domain: read("VITE_COGNITO_DOMAIN"),
    clientId: read("VITE_COGNITO_CLIENT_ID"),
    redirectUri: read("VITE_COGNITO_REDIRECT_URI"),
    logoutUri: read("VITE_COGNITO_LOGOUT_URI") || `${window.location.origin}/`,
    scopes: "openid email profile",
    identityProviders: parseIdentityProviders(
      read("VITE_COGNITO_IDENTITY_PROVIDERS"),
    ),
  };
}

/** Social IdPs enabled in this build (excludes COGNITO). */
export function getSocialProviders(): CognitoIdentityProvider[] {
  if (!isCognitoConfigured()) return [];
  return getCognitoConfig().identityProviders.filter((p) => p !== "COGNITO");
}

export function isEmailAuthEnabled(): boolean {
  if (!isCognitoConfigured()) return false;
  return getCognitoConfig().identityProviders.includes("COGNITO");
}
