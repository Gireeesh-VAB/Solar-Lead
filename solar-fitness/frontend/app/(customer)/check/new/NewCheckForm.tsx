"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Crosshair, IndianRupee, Loader2, MapPin, Search } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { AddressAutocomplete } from "@/components/map/AddressAutocomplete";
import { MapView, type MapPinData } from "@/components/map/MapView";
import { GeocodeUnavailableError, geocodeAddress, reverseGeocode, type GeocodeResult } from "@/lib/maps/geocode";
import { useCreateCheck } from "@/lib/query/hooks";

type Coords = { lat: number; lng: number };

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

export function NewCheckForm() {
  const router = useRouter();
  const createCheck = useCreateCheck();
  const [address, setAddress] = useState("");
  // No coordinates until the user actually supplies some. Previously this
  // started on a hardcoded city centre, which meant a user who never
  // touched the map silently submitted somebody else's rooftop.
  const [coords, setCoords] = useState<Coords | null>(null);
  const [locating, setLocating] = useState(false);
  const [searching, setSearching] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // CON-05. A range rather than one figure because Indian household bills
  // swing hard with the season — a summer bill can be double a winter one,
  // and either endpoint alone sizes the system wrong in an obvious
  // direction. The backend averages them. USN capture happens later, on
  // the result page, once the AI analysis has something to attach it to.
  const [billMode, setBillMode] = useState<"kwh" | "inr">("kwh");
  const [billLow, setBillLow] = useState("");
  const [billHigh, setBillHigh] = useState("");
  const [consumptionLow, setConsumptionLow] = useState("");
  const [consumptionHigh, setConsumptionHigh] = useState("");

  const handleSuggestionPicked = (found: GeocodeResult) => {
    setCoords(found);
    // Say WHICH place matched. "Kukatpally, Hyderabad" and a bare pin are
    // very different levels of confidence that the search worked.
    setNotice(found.formatted ? `Found: ${found.formatted}` : null);
  };

  // Both "use my current location" and a manual pin move (drag/tap) change
  // where the pin actually is — the address text must follow it every
  // time, not just the first time, or it goes on showing wherever the
  // customer last searched while the pin itself has moved somewhere else.
  const relabelPin = async (lat: number, lng: number) => {
    const formatted = await reverseGeocode(lat, lng);
    setAddress(formatted ?? "Pinned location");
  };

  const handleUseCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setNotice("Your browser can't share a location. Tap the map to place your pin instead.");
      return;
    }
    setLocating(true);
    setNotice(null);

    // Fast network fix and precise GPS fix race; the pin lands on whichever
    // answers first and GPS refines it if more accurate.
    let bestAccuracy = Infinity;
    let pending = 2;
    let finished = false;

    const applyPosition = (pos: GeolocationPosition) => {
      const { latitude, longitude, accuracy } = pos.coords;
      if (accuracy >= bestAccuracy) return;
      bestAccuracy = accuracy;
      setCoords({ lat: latitude, lng: longitude });
      void relabelPin(latitude, longitude);
      setLocating(false);
      finished = true;
      setNotice(
        accuracy > 150
          ? `Found you within about ${Math.round(accuracy)}m — drag the pin onto your exact roof to fine-tune it.`
          : null
      );
    };

    const onFailure = (err: GeolocationPositionError) => {
      pending -= 1;
      if (finished) return;
      if (err.code === err.PERMISSION_DENIED) {
        setLocating(false);
        setNotice("Location permission denied. Tap the map to place your pin instead.");
        return;
      }
      if (pending === 0) {
        setLocating(false);
        setNotice("Couldn't get your location. Tap the map to place your pin instead.");
      }
    };

    navigator.geolocation.getCurrentPosition(applyPosition, onFailure, {
      enableHighAccuracy: false,
      timeout: 6000,
      maximumAge: 60000,
    });
    navigator.geolocation.getCurrentPosition(applyPosition, onFailure, {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
    });
  };

  const handleMapMove = (lat: number, lng: number) => {
    setCoords({ lat, lng });
    setNotice(null);
    void relabelPin(lat, lng);
  };

  // AddressAutocomplete is suggestions-only by design (see its own
  // docstring) — this is the explicit fallback for someone who typed a
  // full address and wants to search it directly instead of picking from
  // the dropdown.
  const handleSearch = async () => {
    const query = address.trim();
    if (!query) return;
    setSearching(true);
    setNotice(null);
    try {
      const found = await geocodeAddress(query);
      setCoords(found);
      setAddress(found.formatted ?? query);
      setNotice(found.formatted ? `Found: ${found.formatted}` : null);
    } catch (err) {
      setNotice(
        err instanceof GeocodeUnavailableError
          ? "Address search isn't available right now. Use your current location, or tap the map to place your pin."
          : `Couldn't find "${query}". Try a different search, or tap the map instead.`
      );
    } finally {
      setSearching(false);
    }
  };

  const handleSubmit = async () => {
    if (!coords) return;
    setSubmitError(null);
    try {
      // The existing create-check API is what persists the confirmed
      // coordinates — POST /app/checks {address, lat, lng, siteType, ...}.
      // kWh is primary (FIN-03) — sent only when BOTH are real numbers, a
      // half-filled range is worse than none and the backend would
      // reject it anyway; the ₹ pair is the fallback mode instead.
      const consumptionInput = (() => {
        if (billMode === "kwh") {
          const low = Number.parseFloat(consumptionLow);
          const high = Number.parseFloat(consumptionHigh);
          return Number.isFinite(low) && low > 0 && Number.isFinite(high) && high > 0
            ? { lowestConsumptionKwh: low, highestConsumptionKwh: high }
            : {};
        }
        const low = Number.parseFloat(billLow);
        const high = Number.parseFloat(billHigh);
        return Number.isFinite(low) && low > 0 && Number.isFinite(high) && high > 0
          ? { monthlyBillLowInr: low, monthlyBillHighInr: high }
          : {};
      })();
      const check = await createCheck.mutateAsync({
        address: address.trim() || "Pinned location",
        lat: coords.lat,
        lng: coords.lng,
        siteType: "ROOFTOP_RESIDENTIAL",
        ...consumptionInput,
      });
      router.push(`/check/${check.id}/processing`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Couldn't start the check. Please try again.");
    }
  };

  // Only complain once both are filled — nagging while the user is still
  // typing the first field is noise.
  const billError = (() => {
    const [lowRaw, highRaw] = billMode === "kwh" ? [consumptionLow, consumptionHigh] : [billLow, billHigh];
    const low = Number.parseFloat(lowRaw);
    const high = Number.parseFloat(highRaw);
    if (!lowRaw || !highRaw) return null;
    if (!Number.isFinite(low) || !Number.isFinite(high) || low <= 0 || high <= 0) {
      return billMode === "kwh" ? "Enter both usage figures as numbers." : "Enter both amounts as numbers.";
    }
    if (high < low) return "The highest month should not be less than the lowest.";
    return null;
  })();

  const pins: MapPinData[] = coords
    ? [{ id: "pin", lat: coords.lat, lng: coords.lng, label: address.trim() || "Your pin" }]
    : [];

  const canSubmit = !!coords && !createCheck.isPending;

  return (
    <motion.div initial="hidden" animate="show" variants={stagger} className="space-y-4 pb-4">
      {/* Suggestions come from Google Places through our own backend, so
          the public Maps key never needs Places or Geocoding permission.
          Picking one moves the map and drops the pin; the pin stays
          draggable afterwards, because a street address is rarely the
          exact roof. The Search button beside it is the fallback for
          typing a full address and searching it directly, without
          picking from the dropdown. */}
      <motion.div variants={fadeUp} transition={{ duration: 0.4, ease: "easeOut" }} className="flex items-start gap-2">
        <div className="flex-1">
          <AddressAutocomplete
            value={address}
            onValueChange={setAddress}
            onSelect={handleSuggestionPicked}
            onUnavailable={setNotice}
            disabled={createCheck.isPending}
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={handleSearch}
          disabled={searching || createCheck.isPending || !address.trim()}
          className="h-11 min-h-11 w-11 shrink-0 px-0"
        >
          {searching ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Search size={16} strokeWidth={1.75} aria-hidden="true" />}
          <span className="sr-only">Search</span>
        </Button>
      </motion.div>

      <motion.button
        variants={fadeUp}
        transition={{ duration: 0.4, ease: "easeOut" }}
        type="button"
        onClick={handleUseCurrentLocation}
        disabled={locating}
        className="flex min-h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-paper px-3 py-2.5 text-sm font-medium text-blue outline-none transition-colors hover:border-blue hover:bg-surface focus-visible:border-blue focus-visible:ring-2 focus-visible:ring-blue/20 disabled:opacity-60"
      >
        {locating ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Crosshair size={16} strokeWidth={1.75} aria-hidden="true" />}
        {locating ? "Finding you…" : "Use my current location"}
      </motion.button>

      {notice && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2.5 text-xs text-ink-soft"
          role="status"
        >
          {notice}
        </motion.p>
      )}

      <motion.div variants={fadeUp} transition={{ duration: 0.4, ease: "easeOut" }}>
        <div className="overflow-hidden rounded-[var(--radius-app)] border border-line shadow-[var(--shadow-float)]">
          <MapView pins={pins} center={coords} height={320} interactive onMove={handleMapMove} />
        </div>
        <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-faint">
          <MapPin size={13} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          {coords ? (
            <span>📍 Location selected — drag the pin or tap the map to fine-tune.</span>
          ) : (
            <span>Search, use your location, or tap the map once it appears to drop a pin.</span>
          )}
        </p>
      </motion.div>

      {/* CON-05. Without this the system is sized by roof area alone, which
          is why an ordinary house used to come back at tens of kWp it could
          never use. Optional, so a customer who does not know their bill can
          still get a result. */}
      <motion.div variants={fadeUp} transition={{ duration: 0.4, ease: "easeOut" }}>
        <Card className="p-4">
          <div className="mb-1.5 flex items-center gap-2">
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
              style={{ background: "var(--warn-bg)", color: "var(--amber)" }}
              aria-hidden="true"
            >
              <IndianRupee size={15} strokeWidth={1.75} />
            </span>
            <p className="text-sm font-medium text-ink">Your electricity usage</p>
          </div>
          <p className="mb-2 text-xs leading-relaxed text-ink-soft">
            Give us your least and highest bill in the year — usage changes a lot between seasons, and
            the range helps us size the system to what you actually use.
          </p>
          <div className="mb-3 flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-surface-2 p-1 text-xs">
            <button
              type="button"
              onClick={() => setBillMode("kwh")}
              className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
              style={billMode === "kwh" ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
            >
              Units (kWh)
            </button>
            <button
              type="button"
              onClick={() => setBillMode("inr")}
              className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
              style={billMode === "inr" ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
            >
              Bill amount (₹)
            </button>
          </div>
          {billMode === "kwh" ? (
            <div className="flex items-start gap-2.5">
              <div className="flex-1">
                <label htmlFor="consumption-low" className="mb-1.5 block text-xs font-medium text-ink-faint">
                  Least usage in year
                </label>
                <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2.5 transition-colors focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/15">
                  <input
                    id="consumption-low"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    value={consumptionLow}
                    onChange={(e) => setConsumptionLow(e.target.value)}
                    placeholder="400"
                    className="w-full bg-transparent text-sm text-ink outline-none"
                  />
                  <span className="text-sm text-ink-faint">kWh</span>
                </div>
              </div>
              <div className="flex-1">
                <label htmlFor="consumption-high" className="mb-1.5 block text-xs font-medium text-ink-faint">
                  Highest usage in year
                </label>
                <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2.5 transition-colors focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/15">
                  <input
                    id="consumption-high"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    value={consumptionHigh}
                    onChange={(e) => setConsumptionHigh(e.target.value)}
                    placeholder="900"
                    className="w-full bg-transparent text-sm text-ink outline-none"
                  />
                  <span className="text-sm text-ink-faint">kWh</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2.5">
              <div className="flex-1">
                <label htmlFor="bill-low" className="mb-1.5 block text-xs font-medium text-ink-faint">
                  Least bill in year
                </label>
                <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2.5 transition-colors focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/15">
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
                <label htmlFor="bill-high" className="mb-1.5 block text-xs font-medium text-ink-faint">
                  Highest bill in year
                </label>
                <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2.5 transition-colors focus-within:border-blue focus-within:ring-2 focus-within:ring-blue/15">
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
          )}
          <p className="mt-2 text-xs" style={billError ? { color: "var(--bad)" } : undefined}>
            <span className={billError ? "" : "text-ink-faint"}>
              {billError ?? "Optional — skip it and we'll size by roof space alone."}
            </span>
          </p>
        </Card>
      </motion.div>

      {submitError && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[var(--radius-app)] border px-3 py-2.5 text-xs"
          role="alert"
          style={{ borderColor: "var(--bad)", color: "var(--bad)", background: "var(--bad-bg)" }}
        >
          {submitError}
        </motion.p>
      )}

      {/* Sticky on mobile so the primary action stays reachable without
          hunting for it after scrolling through the map and bill fields —
          parked just above the app's fixed mobile bottom nav. On md+ (where
          that bottom nav disappears and the form sits in a calmer, roomier
          layout) it reverts to a normal in-flow button. */}
      <motion.div
        variants={fadeUp}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-10 -mx-4 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm md:static md:bottom-auto md:z-auto md:mx-0 md:border-0 md:bg-transparent md:px-0 md:py-0 md:backdrop-blur-none"
      >
        <Button
          type="button"
          size="md"
          className="min-h-12 w-full text-base shadow-[var(--shadow-float)]"
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          {createCheck.isPending ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
              Starting…
            </>
          ) : coords ? (
            "Check this location"
          ) : (
            "Place your pin first"
          )}
        </Button>
      </motion.div>
    </motion.div>
  );
}
