/** Barrel for Cognito Hosted UI scaffolding. */

export { AuthBar } from "./AuthBar";
export { CallbackPage } from "./CallbackPage";
export { LandingPage } from "./LandingPage";
export {
  isCognitoConfigured,
  getCognitoConfig,
  getSocialProviders,
  isEmailAuthEnabled,
} from "./config";
export type { CognitoIdentityProvider } from "./config";
export {
  beginLogin,
  completeLoginFromRedirect,
  logout,
  ensureIdToken,
  buildAuthorizeUrl,
  buildSignupUrl,
  exchangeAuthorizationCode,
  refreshTokens,
} from "./oauth";
export type { BeginLoginOptions } from "./oauth";
export { createPkce, base64UrlEncode } from "./pkce";
export {
  getIdToken,
  getTokens,
  setTokens,
  clearTokens,
  isSignedIn,
  isAccessExpired,
  getRefreshToken,
} from "./session";
