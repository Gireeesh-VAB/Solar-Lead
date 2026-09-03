"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Crosshair, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { AddressAutocomplete } from "@/components/map/AddressAutocomplete";
import { MapView, type MapPinData } from "@/components/map/MapView";
import type { GeocodeResult } from "@/lib/maps/geocode";
import { useCreateCheck } from "@/lib/query/hooks";

type Coords = { lat: number; lng: number };

export function NewCheckForm() {
  const router = useRouter();
  const createCheck = useCreateCheck();
  const [address, setAddress] = useState("");
  // No coordinates until the user actually supplies some. Previously this
  // started on a hardcoded city centre, which meant a user who never
  // touched the map silently submitted somebody else's rooftop.
  const [coords, setCoords] = useState<Coords | null>(null);
  const [locating, setLocating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // CON-05. A range rather than one figure because Indian household bills
  // swing hard with the season — a summer bill can be double a winter one,
  // and either endpoint alone sizes the system wrong in an obvious
  // direction. The backend averages them.
  const [billLow, setBillLow] = useState("");
  const [billHigh, setBillHigh] = useState("");

  const handleSuggestionPicked = (found: GeocodeResult) => {
    setCoords(found);
    // Say WHICH place matched. "Kukatpally, Hyderabad" and a bare pin are
    // very different levels of confidence that the search worked.
    setNotice(found.formatted ? `Found: ${found.formatted}` : null);
  };

  const handleUseCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setNotice("Your browser can't share a location. Tap the map to place your pin instead.");
      return;
    }
    setLocating(true);
    setNotice(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        if (!address.trim()) setAddress("My current location");
        setLocating(false);
      },
      (err) => {
        setLocating(false);
        setNotice(
          err.code === err.PERMISSION_DENIED
            ? "Location permission denied. Tap the map to place your pin instead."
            : "Couldn't get your location. Tap the map to place your pin instead."
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  const handleMapMove = (lat: number, lng: number) => {
    setCoords({ lat, lng });
    setNotice(null);
  };

  const handleSubmit = async () => {
    if (!coords) return;
    setSubmitError(null);
    try {
      // The existing create-check API is what persists the confirmed
      // coordinates — POST /app/checks {address, lat, lng, siteType}.
      const low = Number.parseFloat(billLow);
      const high = Number.parseFloat(billHigh);
      const check = await createCheck.mutateAsync({
        address: address.trim() || "Pinned location",
        lat: coords.lat,
        lng: coords.lng,
        siteType: "ROOFTOP_RESIDENTIAL",
        // Sent only when BOTH are real numbers — a half-filled range is
        // worse than none, and the backend would reject it anyway.
        ...(Number.isFinite(low) && low > 0 && Number.isFinite(high) && high > 0
          ? { monthlyBillLowInr: low, monthlyBillHighInr: high }
          : {}),
      });
      router.push(`/check/${check.id}/processing`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Couldn't start the check. Please try again.");
    }
  };

  // Only complain once both are filled — nagging while the user is still
  // typing the first field is noise.
  const billError = (() => {
    const low = Number.parseFloat(billLow);
    const high = Number.parseFloat(billHigh);
    if (!billLow || !billHigh) return null;
    if (!Number.isFinite(low) || !Number.isFinite(high) || low <= 0 || high <= 0) {
      return "Enter both amounts as numbers.";
    }
    if (high < low) return "The highest month should not be less than the lowest.";
    return null;
  })();

  const pins: MapPinData[] = coords
    ? [{ id: "pin", lat: coords.lat, lng: coords.lng, label: address.trim() || "Your pin" }]
    : [];

  return (
    <div className="space-y-4">
      {/* Suggestions come from Google Places through our own backend, so
          the public Maps key never needs Places or Geocoding permission.
          Picking one moves the map and drops the pin; the pin stays
          draggable afterwards, because a street address is rarely the
          exact roof. */}
      <AddressAutocomplete
        value={address}
        onValueChange={setAddress}
        onSelect={handleSuggestionPicked}
        onUnavailable={setNotice}
        disabled={createCheck.isPending}
      />

      <button
        type="button"
        onClick={handleUseCurrentLocation}
        disabled={locating}
        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-paper px-3 py-2 text-sm font-medium text-blue outline-none transition-colors hover:border-blue hover:bg-surface disabled:opacity-60"
      >
        {locating ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Crosshair size={15} strokeWidth={1.75} aria-hidden="true" />}
        {locating ? "Finding you…" : "Use my current location"}
      </button>

      {notice && (
        <p className="rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2 text-xs text-ink-soft" role="status">
          {notice}
        </p>
      )}

      <div>
        <MapView pins={pins} center={coords} height={320} interactive onMove={handleMapMove} />
        <p className="mt-1.5 text-xs text-ink-faint">
          {coords ? (
            <>
              Pin set at <span className="font-mono">{coords.lat.toFixed(6)}, {coords.lng.toFixed(6)}</span> — drag it
              or tap the map to fine-tune.
            </>
          ) : (
            "Search, use your location, or tap the map once it appears to drop a pin."
          )}
        </p>
      </div>

      {/* CON-05. Without this the system is sized by roof area alone, which
          is why an ordinary house used to come back at tens of kWp it could
          never use. Optional, so a customer who does not know their bill can
          still get a result. */}
      <div>
        <p className="mb-1.5 text-sm font-medium text-ink">Your electricity bill</p>
        <p className="mb-2.5 text-xs text-ink-soft">
          Roughly what do you pay in a month? Give us your lowest and highest — bills change a lot
          between seasons, and the range helps us size the system to what you actually use.
        </p>
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <label htmlFor="bill-low" className="mb-1 block text-xs text-ink-faint">
              Lowest month
            </label>
            <div className="flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2">
              <span className="text-sm text-ink-faint">₹</span>
              <input
                id="bill-low"
                type="number"
                inputMode="numeric"
                min={1}
                value={billLow}
                onChange={(e) => setBillLow(e.target.value)}
                placeholder="1,200"
                className="w-full bg-transparent text-sm text-ink outline-none"
              />
            </div>
          </div>
          <div className="flex-1">
            <label htmlFor="bill-high" className="mb-1 block text-xs text-ink-faint">
              Highest month
            </label>
            <div className="flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2">
              <span className="text-sm text-ink-faint">₹</span>
              <input
                id="bill-high"
                type="number"
                inputMode="numeric"
                min={1}
                value={billHigh}
                onChange={(e) => setBillHigh(e.target.value)}
                placeholder="2,400"
                className="w-full bg-transparent text-sm text-ink outline-none"
              />
            </div>
          </div>
        </div>
        <p className="mt-1.5 text-xs text-ink-faint">
          {billError ?? "Optional — skip it and we'll size by roof space alone."}
        </p>
      </div>

      {submitError && (
        <p className="rounded-[var(--radius-app)] border px-3 py-2 text-xs" role="alert" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          {submitError}
        </p>
      )}

      <Button
        type="button"
        size="md"
        className="w-full"
        onClick={handleSubmit}
        disabled={createCheck.isPending || !coords}
      >
        {createCheck.isPending ? "Starting…" : coords ? "Check this location" : "Place your pin first"}
      </Button>
    </div>
  );
}
