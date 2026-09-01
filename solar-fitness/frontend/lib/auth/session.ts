// -----------------------------------------------------------------------------
// Client-side auth session storage — the one place that reads/writes the
// stored bearer token, rather than scattering localStorage calls across
// login/signup/logout/the fetch wrapper.
//
// localStorage can throw (private browsing, storage disabled) or simply not
// exist (server-side render) — every function here is defensive about both.
// -----------------------------------------------------------------------------

export type PortalRole = "customer" | "vendor" | "admin";

export interface StoredSession {
  token: string;
  userId: string;
  role: PortalRole;
  name: string;
  email: string;
}

const SESSION_KEY = "solarfit.session";

// Mirrored alongside localStorage so Server Components (which can't read
// localStorage) can still authenticate outbound requests — see
// lib/api/serverFetch.ts. Not httpOnly: it's set from client-side JS, and
// carries no more exposure than the same token already sitting in
// localStorage right next to it.
const TOKEN_COOKIE = "sf_token";
const TOKEN_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;

function setTokenCookie(token: string): void {
  try {
    document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${TOKEN_COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
  } catch {
    // document.cookie can throw in some locked-down embeds — the session
    // still works client-side via localStorage either way.
  }
}

function clearTokenCookie(): void {
  try {
    document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; samesite=lax`;
  } catch {
    // See setTokenCookie.
  }
}

export function getStoredSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

export function setStoredSession(session: StoredSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable — the session just won't persist across reloads.
  }
  setTokenCookie(session.token);
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Nothing to clean up if storage never worked.
  }
  clearTokenCookie();
}

export function getStoredToken(): string | null {
  return getStoredSession()?.token ?? null;
}

export const ROLE_LANDING: Record<PortalRole, string> = {
  customer: "/home",
  vendor: "/vendor/dashboard",
  admin: "/admin/dashboard",
};
