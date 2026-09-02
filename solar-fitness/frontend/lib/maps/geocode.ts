/**
 * Address -> coordinates, via the Maps JavaScript API's own Geocoder.
 *
 * Deliberately the JS geocoder rather than a server-side call to the REST
 * Geocoding API: the browser already loads Maps JavaScript for the map
 * itself, so this needs no extra key handling and no backend route.
 *
 * Geocoding is a SEPARATE Google API from Maps JavaScript and is enabled
 * separately. On this project's key it is currently not authorised —
 * verified 2026-09-02, both REST (`REQUEST_DENIED`) and JS
 * (`GEOCODER_GEOCODE: REQUEST_DENIED: The webpage is not allowed to use
 * the geocoder`). That failure is surfaced as GeocodeUnavailableError so
 * the caller can tell the user to place the pin by hand instead of
 * fabricating a location. Nothing here needs to change when the API is
 * enabled — it simply starts succeeding.
 */

export class GeocodeUnavailableError extends Error {
  constructor(message = "Geocoding is not enabled for this API key") {
    super(message);
    this.name = "GeocodeUnavailableError";
  }
}

export interface GeocodeResult {
  lat: number;
  lng: number;
  formatted?: string;
}

const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";
const SCRIPT_ID = "google-maps-js-api";

/** Resolves once google.maps is on the page. Reuses the script tag
 *  @vis.gl/react-google-maps may already have added. */
function loadMapsJs(): Promise<typeof google.maps> {
  if (typeof window === "undefined") {
    return Promise.reject(new GeocodeUnavailableError("Geocoding is browser-only"));
  }
  if (window.google?.maps?.Geocoder) return Promise.resolve(window.google.maps);
  if (!API_KEY) return Promise.reject(new GeocodeUnavailableError("No Maps API key configured"));

  return new Promise((resolve, reject) => {
    const done = () => {
      if (window.google?.maps?.Geocoder) resolve(window.google.maps);
      else reject(new GeocodeUnavailableError("Maps JavaScript API failed to load"));
    };

    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", done, { once: true });
      existing.addEventListener("error", () => reject(new GeocodeUnavailableError()), { once: true });
      // Already finished loading before we attached the listener.
      if (window.google?.maps?.Geocoder) resolve(window.google.maps);
      return;
    }

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${API_KEY}&libraries=geocoding&loading=async`;
    script.addEventListener("load", done, { once: true });
    script.addEventListener("error", () => reject(new GeocodeUnavailableError()), { once: true });
    document.head.appendChild(script);
  });
}

export async function geocodeAddress(address: string): Promise<GeocodeResult> {
  const maps = await loadMapsJs();
  const geocoder = new maps.Geocoder();

  let response: google.maps.GeocoderResponse;
  try {
    response = await geocoder.geocode({ address });
  } catch (err) {
    const message = String(err);
    // REQUEST_DENIED means the API isn't enabled for this key — a
    // configuration problem, not a bad address. The two need different
    // messages, so they get different error types.
    if (/REQUEST_DENIED|not allowed to use the geocoder|ApiNotActivated/i.test(message)) {
      throw new GeocodeUnavailableError(message);
    }
    throw new Error(`No match for that address (${message})`);
  }

  const best = response.results?.[0];
  if (!best) throw new Error("No match for that address");

  return {
    lat: best.geometry.location.lat(),
    lng: best.geometry.location.lng(),
    formatted: best.formatted_address,
  };
}
