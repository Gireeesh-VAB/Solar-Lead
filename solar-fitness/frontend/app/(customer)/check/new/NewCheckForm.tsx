"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMapsLibrary } from "@vis.gl/react-google-maps";
import { Crosshair, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { MapView, MapsProvider, type MapPinData } from "@/components/map/MapView";
import { useCreateCheck } from "@/lib/query/hooks";
import type { ConnectionType, RoofMaterial, RoofSlope, RoofType } from "@/lib/types";

const CONNECTION_TYPE_LABEL: Record<ConnectionType, string> = {
  SINGLE_PHASE: "Single phase",
  THREE_PHASE: "Three phase",
};

// Last 12 calendar months, oldest first, as "YYYY-MM" — matches spec
// section 9's Jan..Dec monthly consumption capture.
function last12Months(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

const ROOF_TYPE_LABEL: Record<RoofType, string> = {
  RCC_CONCRETE: "RCC / concrete",
  METAL_SHEET: "Metal sheet",
  GI_SHEET: "GI sheet",
  TILED: "Tiled roof",
  ASBESTOS_SHEET: "Asbestos sheet",
  GROUND_MOUNTED: "Ground-mounted",
  TERRACE: "Terrace",
  OTHER: "Other",
};

const ROOF_MATERIAL_LABEL: Record<RoofMaterial, string> = {
  RCC: "RCC",
  CONCRETE: "Concrete",
  METAL: "Metal",
  TILE: "Tile",
  SHEET: "Sheet",
  OTHER: "Other",
};

const ROOF_SLOPE_LABEL: Record<RoofSlope, string> = {
  FLAT: "Flat",
  LOW: "Low slope",
  MEDIUM: "Medium slope",
  HIGH: "High slope",
};

const DEFAULT_LAT = 17.385;
const DEFAULT_LNG = 78.4867;

// Fallback for when no Google Maps API key is configured (NEXT_PUBLIC_
// GOOGLE_MAPS_API_KEY) — same "unavailable, don't crash" discipline as
// MapView's own SVG fallback. Deterministic, not a real geocode.
function offlineMockGeocode(address: string): { lat: number; lng: number } {
  let hash = 0;
  for (let i = 0; i < address.length; i++) hash = (hash * 31 + address.charCodeAt(i)) >>> 0;
  const latOffset = ((hash % 2000) / 10000) * (hash % 2 === 0 ? 1 : -1);
  const lngOffset = (((hash >> 3) % 2000) / 10000) * (hash % 3 === 0 ? 1 : -1);
  return { lat: DEFAULT_LAT + latOffset, lng: DEFAULT_LNG + lngOffset };
}

function geolocationErrorMessage(err: GeolocationPositionError): string {
  switch (err.code) {
    case err.PERMISSION_DENIED:
      return "Location access was denied. Allow location access in your browser, or search/tap the map instead.";
    case err.POSITION_UNAVAILABLE:
      return "Your location couldn't be determined. Try searching or tapping the map instead.";
    case err.TIMEOUT:
      return "Finding your location timed out. Try again, or search/tap the map instead.";
    default:
      return "Couldn't get your location. Try searching or tapping the map instead.";
  }
}

export function NewCheckForm() {
  return (
    <MapsProvider>
      <NewCheckFormInner />
    </MapsProvider>
  );
}

function NewCheckFormInner() {
  const router = useRouter();
  const createCheck = useCreateCheck();
  const geocodingLibrary = useMapsLibrary("geocoding");
  const placesLibrary = useMapsLibrary("places");
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState(DEFAULT_LAT);
  const [lng, setLng] = useState(DEFAULT_LNG);
  const [pinPlaced, setPinPlaced] = useState(false);
  const [locating, setLocating] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<google.maps.places.PlacePrediction[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [resolvingSuggestion, setResolvingSuggestion] = useState(false);
  const sessionTokenRef = useRef<google.maps.places.AutocompleteSessionToken | null>(null);
  const suggestionsBoxRef = useRef<HTMLDivElement>(null);
  const skipNextFetchRef = useRef(false);
  const [roofType, setRoofType] = useState<RoofType | "">("");
  const [roofMaterial, setRoofMaterial] = useState<RoofMaterial | "">("");
  const [roofSlope, setRoofSlope] = useState<RoofSlope | "">("");
  const [roofConstructionYear, setRoofConstructionYear] = useState("");
  const [electricityBoard, setElectricityBoard] = useState("");
  const [consumerNumber, setConsumerNumber] = useState("");
  const [connectionType, setConnectionType] = useState<ConnectionType | "">("");
  const [sanctionedLoadKw, setSanctionedLoadKw] = useState("");
  const [monthlyUnits, setMonthlyUnits] = useState<Record<string, string>>({});
  const [batteryRequired, setBatteryRequired] = useState(false);
  const [backupRequired, setBackupRequired] = useState(false);
  const [requiredBackupHours, setRequiredBackupHours] = useState("");
  const [criticalLoads, setCriticalLoads] = useState("");

  // Autocomplete dropdown: fetch suggestions as the user types (debounced),
  // biased the same way as the plain-search geocode below. Skipped right
  // after we set `address` ourselves (a selection, a geolocate result, a
  // search result) so accepting a suggestion doesn't immediately reopen
  // the dropdown with a fresh query for its own resolved text.
  useEffect(() => {
    if (skipNextFetchRef.current) {
      skipNextFetchRef.current = false;
      return;
    }
    const query = address.trim();
    if (!placesLibrary || query.length < 3) {
      setSuggestions([]);
      setSuggestionsOpen(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (!sessionTokenRef.current) {
        sessionTokenRef.current = new placesLibrary.AutocompleteSessionToken();
      }
      try {
        const { suggestions: results } = await placesLibrary.AutocompleteSuggestion.fetchAutocompleteSuggestions({
          input: query,
          locationBias: { north: lat + 0.5, south: lat - 0.5, east: lng + 0.5, west: lng - 0.5 },
          region: "in",
          sessionToken: sessionTokenRef.current,
        });
        if (cancelled) return;
        setSuggestions(results.map((s) => s.placePrediction).filter((p): p is google.maps.places.PlacePrediction => p !== null));
        setSuggestionsOpen(true);
      } catch {
        if (!cancelled) setSuggestions([]);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address, placesLibrary]);

  const selectSuggestion = async (prediction: google.maps.places.PlacePrediction) => {
    setSuggestionsOpen(false);
    setResolvingSuggestion(true);
    setError(null);
    try {
      const place = prediction.toPlace();
      await place.fetchFields({ fields: ["location", "formattedAddress"] });
      if (place.location) {
        setLat(place.location.lat());
        setLng(place.location.lng());
        setPinPlaced(true);
      }
      skipNextFetchRef.current = true;
      setAddress(place.formattedAddress || prediction.text.text);
      sessionTokenRef.current = null; // session ends once a place is picked
    } catch {
      setError("Couldn't load that place. Try a different suggestion, or tap the map instead.");
    } finally {
      setResolvingSuggestion(false);
    }
  };

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (suggestionsBoxRef.current && !suggestionsBoxRef.current.contains(e.target as Node)) {
        setSuggestionsOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const handleSearch = async () => {
    setSuggestionsOpen(false);
    const query = address.trim();
    if (!query) return;
    setSearching(true);
    setError(null);
    try {
      if (geocodingLibrary) {
        // Bias toward the current pin (soft — doesn't exclude other matches)
        // and toward India generally, so an ambiguous query (a landmark or
        // area name with no city/state) doesn't resolve to a same-named
        // place on the other side of the world instead of the one nearby.
        const { results } = await new geocodingLibrary.Geocoder().geocode({
          address: query,
          bounds: {
            north: lat + 0.5,
            south: lat - 0.5,
            east: lng + 0.5,
            west: lng - 0.5,
          },
          region: "in",
        });
        const first = results[0];
        if (!first) {
          setError(`No location found for "${query}".`);
          return;
        }
        setLat(first.geometry.location.lat());
        setLng(first.geometry.location.lng());
        skipNextFetchRef.current = true;
        setAddress(first.formatted_address || query);
        setPinPlaced(true);
      } else {
        // No Maps API key configured — deterministic offline fallback.
        const result = offlineMockGeocode(query);
        setLat(result.lat);
        setLng(result.lng);
        setPinPlaced(true);
      }
    } catch {
      setError(`Couldn't find "${query}". Try a different search, or tap the map instead.`);
    } finally {
      setSearching(false);
    }
  };

  const handleUseCurrentLocation = () => {
    if (!("geolocation" in navigator)) {
      setError("Your browser doesn't support geolocation. Search or tap the map instead.");
      return;
    }
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setLat(latitude);
        setLng(longitude);
        setPinPlaced(true);
        skipNextFetchRef.current = true;
        if (geocodingLibrary) {
          try {
            const { results } = await new geocodingLibrary.Geocoder().geocode({
              location: { lat: latitude, lng: longitude },
            });
            if (results[0]) setAddress(results[0].formatted_address);
            else if (!address.trim()) setAddress("Your current location");
          } catch {
            if (!address.trim()) setAddress("Your current location");
          }
        } else if (!address.trim()) {
          setAddress("Your current location");
        }
        setLocating(false);
      },
      (err) => {
        setError(geolocationErrorMessage(err));
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 }
    );
  };

  const handleMapMove = (newLat: number, newLng: number) => {
    setLat(newLat);
    setLng(newLng);
    setPinPlaced(true);
  };

  const handleSubmit = async () => {
    const check = await createCheck.mutateAsync({
      address: address.trim() || "Pinned location",
      lat,
      lng,
      siteType: "ROOFTOP_RESIDENTIAL",
      roofType: roofType || undefined,
      roofMaterial: roofMaterial || undefined,
      roofSlope: roofSlope || undefined,
      roofConstructionYear: roofConstructionYear ? Number(roofConstructionYear) : undefined,
      electricityBoard: electricityBoard.trim() || undefined,
      consumerNumber: consumerNumber.trim() || undefined,
      connectionType: connectionType || undefined,
      sanctionedLoadKw: sanctionedLoadKw ? Number(sanctionedLoadKw) : undefined,
      monthlyConsumptionKwh: Object.entries(monthlyUnits)
        .filter(([, units]) => units.trim() !== "")
        .map(([month, units]) => ({ month, unitsKwh: Number(units) })),
      batteryRequired,
      backupRequired,
      requiredBackupHours: requiredBackupHours ? Number(requiredBackupHours) : undefined,
      criticalLoads: criticalLoads.trim() || undefined,
    });
    router.push(`/check/${check.id}/processing`);
  };

  const pins: MapPinData[] = [{ id: "pin", lat, lng, label: address.trim() || "Your pin" }];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1" ref={suggestionsBoxRef}>
          <Search size={15} strokeWidth={1.75} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden="true" />
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onFocus={() => {
              if (suggestions.length > 0) setSuggestionsOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                setSuggestionsOpen(false);
                void handleSearch();
              } else if (e.key === "Escape") {
                setSuggestionsOpen(false);
              }
            }}
            placeholder="Search an address or place…"
            role="combobox"
            aria-expanded={suggestionsOpen}
            aria-autocomplete="list"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper py-2 pl-9 pr-3 text-sm text-ink outline-none focus:border-blue"
          />
          {suggestionsOpen && suggestions.length > 0 && (
            <ul className="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-[var(--radius-app)] border border-line bg-surface py-1 shadow-[var(--shadow-float)]">
              {suggestions.map((s) => (
                <li key={s.placeId}>
                  <button
                    type="button"
                    onClick={() => void selectSuggestion(s)}
                    className="flex w-full flex-col items-start gap-0 px-3 py-2 text-left text-sm hover:bg-paper"
                  >
                    <span className="text-ink">{s.mainText?.text ?? s.text.text}</span>
                    {s.secondaryText && <span className="text-xs text-ink-faint">{s.secondaryText.text}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Button type="button" variant="secondary" onClick={handleSearch} disabled={searching || resolvingSuggestion || !address.trim()}>
          {searching || resolvingSuggestion ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : "Search"}
        </Button>
      </div>

      <button
        type="button"
        onClick={handleUseCurrentLocation}
        disabled={locating}
        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-paper px-3 py-2 text-sm font-medium text-blue outline-none transition-colors hover:border-blue hover:bg-surface disabled:opacity-60"
      >
        {locating ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Crosshair size={15} strokeWidth={1.75} aria-hidden="true" />}
        {locating ? "Finding you…" : "Use my current location"}
      </button>

      {error && (
        <p role="alert" className="text-xs" style={{ color: "var(--bad)" }}>
          {error}
        </p>
      )}

      <div>
        <MapView pins={pins} height={320} interactive onMove={handleMapMove} standalone={false} />
        <p className="mt-1.5 text-xs text-ink-faint">
          {pinPlaced ? "Pin set — drag it or tap elsewhere on the map to fine-tune." : "Search, use your location, or tap the map to drop a pin."}
        </p>
      </div>

      <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-paper p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Roof details (optional, helps our estimate)</p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="roof-type" className="mb-1 block text-xs text-ink-soft">
              Roof type
            </label>
            <select
              id="roof-type"
              value={roofType}
              onChange={(e) => setRoofType(e.target.value as RoofType | "")}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not sure</option>
              {(Object.keys(ROOF_TYPE_LABEL) as RoofType[]).map((t) => (
                <option key={t} value={t}>
                  {ROOF_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="roof-material" className="mb-1 block text-xs text-ink-soft">
              Roof material
            </label>
            <select
              id="roof-material"
              value={roofMaterial}
              onChange={(e) => setRoofMaterial(e.target.value as RoofMaterial | "")}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not sure</option>
              {(Object.keys(ROOF_MATERIAL_LABEL) as RoofMaterial[]).map((m) => (
                <option key={m} value={m}>
                  {ROOF_MATERIAL_LABEL[m]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="roof-slope" className="mb-1 block text-xs text-ink-soft">
              Roof slope
            </label>
            <select
              id="roof-slope"
              value={roofSlope}
              onChange={(e) => setRoofSlope(e.target.value as RoofSlope | "")}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not sure</option>
              {(Object.keys(ROOF_SLOPE_LABEL) as RoofSlope[]).map((s) => (
                <option key={s} value={s}>
                  {ROOF_SLOPE_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="roof-construction-year" className="mb-1 block text-xs text-ink-soft">
              Construction year
            </label>
            <input
              id="roof-construction-year"
              type="number"
              min={1900}
              max={2100}
              placeholder="e.g. 2015"
              value={roofConstructionYear}
              onChange={(e) => setRoofConstructionYear(e.target.value)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>
      </div>

      <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-paper p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Electricity connection (optional, from your bill)</p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="electricity-board" className="mb-1 block text-xs text-ink-soft">
              Electricity board
            </label>
            <input
              id="electricity-board"
              value={electricityBoard}
              onChange={(e) => setElectricityBoard(e.target.value)}
              placeholder="e.g. TSSPDCL"
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label htmlFor="consumer-number" className="mb-1 block text-xs text-ink-soft">
              Consumer number
            </label>
            <input
              id="consumer-number"
              value={consumerNumber}
              onChange={(e) => setConsumerNumber(e.target.value)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label htmlFor="connection-type" className="mb-1 block text-xs text-ink-soft">
              Connection type
            </label>
            <select
              id="connection-type"
              value={connectionType}
              onChange={(e) => setConnectionType(e.target.value as ConnectionType | "")}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not sure</option>
              {(Object.keys(CONNECTION_TYPE_LABEL) as ConnectionType[]).map((c) => (
                <option key={c} value={c}>
                  {CONNECTION_TYPE_LABEL[c]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="sanctioned-load" className="mb-1 block text-xs text-ink-soft">
              Sanctioned load (kW)
            </label>
            <input
              id="sanctioned-load"
              type="number"
              min={0}
              value={sanctionedLoadKw}
              onChange={(e) => setSanctionedLoadKw(e.target.value)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs text-ink-soft">Last 12 months&apos; consumption (kWh, from your bills — optional)</p>
          <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
            {last12Months().map((month) => (
              <div key={month}>
                <label htmlFor={`consumption-${month}`} className="mb-0.5 block text-[10px] text-ink-faint">
                  {monthLabel(month)}
                </label>
                <input
                  id={`consumption-${month}`}
                  type="number"
                  min={0}
                  value={monthlyUnits[month] ?? ""}
                  onChange={(e) => setMonthlyUnits((prev) => ({ ...prev, [month]: e.target.value }))}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-1.5 py-1 text-xs text-ink"
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-paper p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Battery / backup (optional)</p>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={batteryRequired} onChange={(e) => setBatteryRequired(e.target.checked)} />
            Interested in battery storage
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={backupRequired} onChange={(e) => setBackupRequired(e.target.checked)} />
            Need power backup
          </label>
        </div>
        {backupRequired && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor="backup-hours" className="mb-1 block text-xs text-ink-soft">
                Required backup hours
              </label>
              <input
                id="backup-hours"
                type="number"
                min={0}
                value={requiredBackupHours}
                onChange={(e) => setRequiredBackupHours(e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </div>
            <div>
              <label htmlFor="critical-loads" className="mb-1 block text-xs text-ink-soft">
                Critical loads (what must stay on)
              </label>
              <input
                id="critical-loads"
                value={criticalLoads}
                onChange={(e) => setCriticalLoads(e.target.value)}
                placeholder="e.g. fridge, lights, Wi-Fi router"
                className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </div>
          </div>
        )}
      </div>

      <Button
        type="button"
        size="md"
        className="w-full"
        onClick={handleSubmit}
        disabled={createCheck.isPending}
      >
        {createCheck.isPending ? "Starting…" : "Check this location"}
      </Button>
    </div>
  );
}
