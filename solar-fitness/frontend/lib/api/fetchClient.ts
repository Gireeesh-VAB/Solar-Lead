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

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
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

  if (response.status === 401) {
    // The stored token is missing/expired/invalid server-side — clear it so
    // the next page load reflects "logged out" instead of a stale session.
    clearStoredSession();
  }

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

  if (response.status === 401) clearStoredSession();
  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}
