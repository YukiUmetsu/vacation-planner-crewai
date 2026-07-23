/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USE_DEMO_DATA?: string;
  readonly VITE_COGNITO_DOMAIN?: string;
  readonly VITE_COGNITO_CLIENT_ID?: string;
  readonly VITE_COGNITO_REDIRECT_URI?: string;
  readonly VITE_COGNITO_LOGOUT_URI?: string;
  /** Comma-separated Cognito IdPs, e.g. COGNITO,Google,Facebook */
  readonly VITE_COGNITO_IDENTITY_PROVIDERS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
