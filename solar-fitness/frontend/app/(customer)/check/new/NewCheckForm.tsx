"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Crosshair, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { MapView, type MapPinData } from "@/components/map/MapView";
import { useCreateCheck } from "@/lib/query/hooks";

const DEFAULT_LAT = 17.385;
const DEFAULT_LNG = 78.4867;
const CURRENT_LOCATION_LAT = 17.4239;
const CURRENT_LOCATION_LNG = 78.4738;

// Deterministic mock "geocode": turns free-text address into a small,
// repeatable offset near the default city center so results feel stable.
function mockGeocode(address: string): { lat: number; lng: number } {
  let hash = 0;
  for (let i = 0; i < address.length; i++) hash = (hash * 31 + address.charCodeAt(i)) >>> 0;
  const latOffset = ((hash % 2000) / 10000) * (hash % 2 === 0 ? 1 : -1);
  const lngOffset = (((hash >> 3) % 2000) / 10000) * (hash % 3 === 0 ? 1 : -1);
  return { lat: DEFAULT_LAT + latOffset, lng: DEFAULT_LNG + lngOffset };
}

export function NewCheckForm() {
  const router = useRouter();
  const createCheck = useCreateCheck();
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState(DEFAULT_LAT);
  const [lng, setLng] = useState(DEFAULT_LNG);
  const [pinPlaced, setPinPlaced] = useState(false);
  const [locating, setLocating] = useState(false);
  const [searching, setSearching] = useState(false);

  const handleSearch = async () => {
    if (!address.trim()) return;
    setSearching(true);
    await new Promise((r) => setTimeout(r, 450));
    const result = mockGeocode(address.trim());
    setLat(result.lat);
    setLng(result.lng);
    setPinPlaced(true);
    setSearching(false);
  };

  const handleUseCurrentLocation = async () => {
    setLocating(true);
    // Simulated geolocation — a real integration would call
    // navigator.geolocation.getCurrentPosition here.
    await new Promise((r) => setTimeout(r, 800));
    setLat(CURRENT_LOCATION_LAT);
    setLng(CURRENT_LOCATION_LNG);
    if (!address.trim()) setAddress("Your current location");
    setPinPlaced(true);
    setLocating(false);
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
    });
    router.push(`/check/${check.id}/processing`);
  };

  const pins: MapPinData[] = [{ id: "pin", lat, lng, label: address.trim() || "Your pin" }];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search size={15} strokeWidth={1.75} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden="true" />
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleSearch();
              }
            }}
            placeholder="Search an address or place…"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper py-2 pl-9 pr-3 text-sm text-ink outline-none focus:border-blue"
          />
        </div>
        <Button type="button" variant="secondary" onClick={handleSearch} disabled={searching || !address.trim()}>
          {searching ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : "Search"}
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

      <div>
        <MapView pins={pins} height={320} interactive onMove={handleMapMove} />
        <p className="mt-1.5 text-xs text-ink-faint">
          {pinPlaced ? "Pin set — drag it or tap elsewhere on the map to fine-tune." : "Search, use your location, or tap the map to drop a pin."}
        </p>
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
