"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Crosshair, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { AddressAutocomplete } from "@/components/map/AddressAutocomplete";
import { MapView, type MapPinData } from "@/components/map/MapView";
import { GeocodeUnavailableError, geocodeAddress, reverseGeocode, type GeocodeResult } from "@/lib/maps/geocode";
import { useCreateCheck } from "@/lib/query/hooks";
import type { ConnectionType, RoofMaterial, RoofSlope, RoofType } from "@/lib/types";

type Coords = { lat: number; lng: number };

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
  // direction. The backend averages them.
  const [billLow, setBillLow] = useState("");
  const [billHigh, setBillHigh] = useState("");

  // Roof Information (customer self-report at intake) — a rough
  // description is enough to shape the initial feasibility check; the
  // vendor's own in-person structural assessment is the source of truth
  // once a survey happens, not these. All optional.
  const [roofType, setRoofType] = useState<RoofType | "">("");
  const [roofMaterial, setRoofMaterial] = useState<RoofMaterial | "">("");
  const [roofSlope, setRoofSlope] = useState<RoofSlope | "">("");
  const [roofConstructionYear, setRoofConstructionYear] = useState("");

  // Electrical Information + Electricity Consumption (customer self-report,
  // from the customer's own bill) — the vendor's own in-person electrical
  // inspection is a separate, later capture on the vendor_jobs row.
  const [electricityBoard, setElectricityBoard] = useState("");
  const [consumerNumber, setConsumerNumber] = useState("");
  const [connectionType, setConnectionType] = useState<ConnectionType | "">("");
  const [sanctionedLoadKw, setSanctionedLoadKw] = useState("");
  const [monthlyUnits, setMonthlyUnits] = useState<Record<string, string>>({});

  // Battery Requirement (spec section 14) — customer's own interest/need.
  const [batteryRequired, setBatteryRequired] = useState(false);
  const [backupRequired, setBackupRequired] = useState(false);
  const [requiredBackupHours, setRequiredBackupHours] = useState("");
  const [criticalLoads, setCriticalLoads] = useState("");

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
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        setCoords({ lat: latitude, lng: longitude });
        await relabelPin(latitude, longitude);
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
          exact roof. The Search button beside it is the fallback for
          typing a full address and searching it directly, without
          picking from the dropdown. */}
      <div className="flex items-start gap-2">
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
        >
          {searching ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Search size={15} strokeWidth={1.75} aria-hidden="true" />}
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
