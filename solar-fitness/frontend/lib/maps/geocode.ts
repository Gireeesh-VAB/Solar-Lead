/**
 * Address -> coordinates, via our own backend.
 *
 * Previously this used the Maps JavaScript API's built-in Geocoder,
 * because the browser already loads Maps JS for the map itself. That
 * needed no backend route — but it did need the PUBLIC key to carry
 * Geocoding permission, and that key is embedded in the bundle where
 * anyone can read it. Google refused it outright (`REQUEST_DENIED: The
 * webpage is not allowed to use the geocoder`), and the fix would have
 * been to widen a key that anyone can copy and spend.
 *
 * So the server geocodes instead, with its own key that never reaches the
 * browser and can be IP-restricted. The public Maps key stays narrow —
 * Maps JavaScript only, which is all the map needs.
 *
 * The exported shape is unchanged, so callers did not have to move.
 */

import { apiFetch } from "@/lib/api/fetchClient";

export class GeocodeUnavailableError extends Error {
  constructor(message = "Address search is unavailable") {
    super(message);
    this.name = "GeocodeUnavailableError";
  }
}

export interface GeocodeResult {
  lat: number;
  lng: number;
  formatted?: string;
}

export interface AddressSuggestion {
  placeId: string;
  description: string;
}

/**
 * Groups a burst of typing and the resolve that follows into ONE billable
 * Places session. Without a token Google bills every keystroke separately.
 * Mint one when the user starts typing, discard it once they pick.
 */
export function newSessionToken(): string {
  return globalThis.crypto?.randomUUID?.() ?? `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Ranked suggestions for partial input.
 *
 * Returns [] rather than throwing when there is nothing to show — a
 * half-typed word with no matches is ordinary, and a dropdown that
 * flashes an error on every keystroke is unusable. Real failures still
 * throw, so the caller can distinguish "nothing yet" from "search is
 * down".
 */
export async function suggestAddresses(
  query: string,
  sessionToken?: string,
  signal?: AbortSignal
): Promise<AddressSuggestion[]> {
  if (!query.trim()) return [];
  const response = await apiFetch<{ suggestions: AddressSuggestion[] }>("/app/geocode/suggest", {
    query: { q: query, session: sessionToken },
    signal,
  });
  return response.suggestions ?? [];
}

/** Resolves a suggestion the user actually picked, by its place id. */
export async function resolveSuggestion(
  placeId: string,
  sessionToken?: string
): Promise<GeocodeResult> {
  return fetchPoint({ placeId, session: sessionToken });
}

interface GeocodeResponse {
  found: boolean;
  lat: number | null;
  lng: number | null;
  formatted: string | null;
}

/**
 * Resolves a free-text address.
 *
 * Two failure modes, deliberately different types, because they need
 * different words in front of the customer:
 *
 *   GeocodeUnavailableError — search itself is down or unconfigured.
 *     Nothing the customer typed is wrong; tell them to place the pin.
 *   Error — Google looked and found nothing. Their input is the thing to
 *     change; suggest a nearby landmark.
 */
export async function geocodeAddress(address: string): Promise<GeocodeResult> {
  return fetchPoint({ address });
}

async function fetchPoint(query: Record<string, string | undefined>): Promise<GeocodeResult> {
  let response: GeocodeResponse;
  try {
    response = await apiFetch<GeocodeResponse>("/app/geocode", { query });
  } catch (err) {
    // The backend answers 503 when its own key is denied or Google is
    // unreachable — a configuration or outage problem, never a bad
    // address. Anything else (network down, session expired) lands here
    // too, and is equally not the customer's fault.
    throw new GeocodeUnavailableError(err instanceof Error ? err.message : String(err));
  }

  if (!response.found || response.lat === null || response.lng === null) {
    throw new Error("No match for that address");
  }

  return {
    lat: response.lat,
    lng: response.lng,
    formatted: response.formatted ?? undefined,
  };
}
