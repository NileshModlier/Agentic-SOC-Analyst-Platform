export const SESSION_COOKIE = "soc_session";

export type Role = "analyst" | "reviewer" | "admin";

export type SessionClaims = {
  sub: string;
  role: Role;
  name: string;
  tenantId: string;
  exp: number;
};

export function sessionSecret() {
  return process.env.CONSOLE_SESSION_SECRET || "dev-console-session";
}

function bytesToBase64Url(bytes: Uint8Array) {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/g, "");
}

function base64UrlToBytes(value: string) {
  const pad = value.length % 4 === 0 ? "" : "=".repeat(4 - (value.length % 4));
  const binary = atob(value.replaceAll("-", "+").replaceAll("_", "/") + pad);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function hmac(secret: string, payload: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return bytesToBase64Url(new Uint8Array(signature));
}

function same(left: string, right: string) {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return diff === 0;
}

export async function sealSession(claims: SessionClaims, secret = sessionSecret()) {
  const payload = bytesToBase64Url(new TextEncoder().encode(JSON.stringify(claims)));
  return `${payload}.${await hmac(secret, payload)}`;
}

export async function openSession(token: string | undefined, secret = sessionSecret()): Promise<SessionClaims | null> {
  if (!token) return null;
  const [payload, signature] = token.split(".");
  if (!payload || !signature || token.split(".").length !== 2) return null;
  if (!same(signature, await hmac(secret, payload))) return null;
  try {
    const claims = JSON.parse(new TextDecoder().decode(base64UrlToBytes(payload))) as SessionClaims;
    if (!claims.exp || claims.exp < Date.now() / 1000) return null;
    if (claims.role !== "analyst" && claims.role !== "reviewer" && claims.role !== "admin") return null;
    if (!claims.tenantId || !claims.name || !claims.sub) return null;
    return claims;
  } catch {
    return null;
  }
}
