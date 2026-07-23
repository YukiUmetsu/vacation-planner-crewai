/**
 * PKCE (Proof Key for Code Exchange, “pixy”) — verifier + S256 challenge.
 *
 * Spec sketch:
 * 1. Generate a high-entropy `code_verifier` (43–128 chars, URL-safe).
 * 2. `code_challenge` = BASE64URL(SHA-256(verifier)) without padding.
 */

export type PkcePair = {
  verifier: string;
  challenge: string;
};

/** URL-safe base64 without padding. */
export function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function createPkce(): Promise<PkcePair> {
  const random = new Uint8Array(32);
  crypto.getRandomValues(random);
  const verifier = base64UrlEncode(random.buffer);
  const challenge = base64UrlEncode(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)),
  );
  return { verifier, challenge };
}
