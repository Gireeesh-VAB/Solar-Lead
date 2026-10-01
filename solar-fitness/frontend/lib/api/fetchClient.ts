// -----------------------------------------------------------------------------
// Shared fetch wrapper for lib/api/client.ts's real (non-mock) functions.
//
// One place for: base URL resolution, JSON encode/decode, bearer-token
// injection from the stored session, and mapping a non-2xx response to
// ApiError — every client.ts function calls apiFetch() instead of building
// its own fetch() call.
// -----------------------------------------------------------------------------

import { clearStoredSession, getStoredToken } from "@/lib/auth/session";

export class ApiError extends Error {
  constructor(
    message: string,
    public status = 500
  ) {
    super(message);
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type QueryValue = string | number | boolean | undefined | null;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(path.replace(/^\//, ""), BASE_URL.endsWith("/") ? BASE_URL : `${BASE_URL}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

// Paths that legitimately return 401 for reasons other than "the stored
// session expired" (bad credentials) — must not trigger the global
// clear-and-redirect below, or a failed login attempt would bounce the user
// away from the login form instead of showing "invalid email or password".
const AUTH_ENDPOINTS = ["/app/auth/login", "/app/auth/signup"];

function handleUnauthorized(path: string): void {
  if (AUTH_ENDPOINTS.some((endpoint) => path.startsWith(endpoint))) return;
  clearStoredSession();
  // The stored token is missing/expired/invalid server-side. Force navigation
  // to /login instead of leaving the caller to render a stale/broken page —
  // AuthGuard only catches this on the *next* mount, not the current one.
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    // A hard navigation is intentional here, not just the router: this file
    // has no access to useRouter (it's a plain module, not a component), and
    // a full reload is what actually drops any stale React Query cache/state
    // built up under the now-invalid session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
}

// FastAPI's 422 shape: detail is an array of {loc, msg, type}, one per
// invalid field — not a string. Left unhandled, callers were showing the
// raw JSON.stringify() of that array to the user instead of readable text.
function describeValidationErrors(detail: unknown[]): string | undefined {
  const messages = detail
    .map((item) => {
      if (!item || typeof item !== "object" || !("msg" in item)) return undefined;
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      if (typeof msg !== "string") return undefined;
      const field = Array.isArray(loc) ? loc.filter((part) => part !== "body").pop() : undefined;
      return field ? `${field}: ${msg}` : msg;
    })
    .filter((m): m is string => !!m);
  return messages.length ? messages.join("; ") : undefined;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return describeValidationErrors(detail) ?? JSON.stringify(detail);
      if (detail !== undefined) return JSON.stringify(detail);
    }
  } catch {
    // Response body wasn't JSON (or was empty) — fall through to the status text.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

/** Every lib/api/client.ts function goes through this. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (response.status === 401) handleUnauthorized(path);

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** For the two endpoints that take a file upload (multipart/form-data). */
export async function apiUpload<T>(
  path: string,
  formData: FormData,
  options: { method?: "POST" | "PUT"; query?: Record<string, QueryValue> } = {}
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "POST",
    headers,
    body: formData,
  });

  if (response.status === 401) handleUnauthorized(path);
  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}
