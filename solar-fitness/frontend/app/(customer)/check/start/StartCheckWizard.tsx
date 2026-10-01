"use client";

// The premium, map-driven "Start Solar Check" flow:
//
//   Locate -> Select Building (Crop or Freehand) -> Adjust Boundary
//   -> Confirm Building -> Review & Start
//
// All five steps live in ONE client component with local step state,
// rather than one Next.js route per step. Reasons, not a default:
//  - A full-screen GoogleMap/APIProvider mount must survive step changes
//    (MapView's own smooth zoom-to-building animation would restart on
//    every route navigation), and there is genuinely no check/site id to
//    key a route on until the customer has already picked a building and
//    cropped it — creating the check earlier would mean either running
//    analysis against an unconfirmed rectangle, or passing a whole
//    polygon through query params/sessionStorage across navigations.
//  - The new StepIndicator reads far more simply against one component's
//    state than against the router's history stack.
//
// The existing check/new/NewCheckForm.tsx (address form, no map-driven
// building selection) is left in place, unmodified, as a fallback path —
// this is an addition, not a replacement.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  ClipboardCheck,
  Compass,
  Crosshair,
  Gauge,
  IdCard,
  Loader2,
  MapPinned,
  Search,
  TriangleAlert,
} from "lucide-react";
import { AddressAutocomplete } from "@/components/map/AddressAutocomplete";
import { BuildingSelector, type BuildingSelectionResult } from "@/components/map/BuildingSelector";
import { MapView } from "@/components/map/MapView";
import { RoofCropEditor } from "@/components/map/RoofCropEditor";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { polygonCentroid } from "@/lib/geo/area";
import { Badge, Card, Button } from "@/components/ui/Primitives";
import { BuildingConfirmationPanel } from "@/components/wizard/BuildingConfirmationPanel";
import { StepIndicator, type WizardStepMeta } from "@/components/wizard/StepIndicator";
import { useT } from "@/lib/i18n/LanguageContext";
import type { RoofPitchResult } from "@/lib/api/client";
import {
  GeocodeUnavailableError,
  geocodeAddress,
  reverseGeocode,
  type GeocodeResult,
} from "@/lib/maps/geocode";
import { useCreateCheck, useRoofPitchAtPoint } from "@/lib/query/hooks";

type WizardStep = "locate" | "select-building" | "adjust-boundary" | "confirm-building" | "review";

const STEP_META: { key: WizardStep; labelKey: string; labelFallback: string }[] = [
  { key: "locate", labelKey: "wizard.stepLocate", labelFallback: "Locate" },
  { key: "select-building", labelKey: "wizard.stepSelectBuilding", labelFallback: "Select building" },
  { key: "adjust-boundary", labelKey: "wizard.stepAdjustBoundary", labelFallback: "Adjust boundary" },
  { key: "confirm-building", labelKey: "wizard.stepConfirmBuilding", labelFallback: "Confirm building" },
  { key: "review", labelKey: "wizard.stepReview", labelFallback: "Review" },
];

// Matches MapView's own BUILDING_ZOOM — the zoom class this wizard's
// building-selection/adjust steps operate at, recorded as map metadata
// so the same satellite view is reproducible later without storing
// image bytes (VIS-06's no-imagery-retention policy).
const WIZARD_MAP_ZOOM = 20;

// Shared step-change transition — a restrained fade/slide, matched to the
// motion language of the premium home screen (HomeClient's fadeUp), but
// short and non-repeating: this is a utility flow, not a marketing page.
const stepVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

// api.RoofPitchResult.orientation is the 16-point abbreviation
// (compassDirection() in lib/types.ts) — spelled out here only for this
// card's display, matching the "South-East" style the product asked for.
const COMPASS_FULL_NAME: Record<string, string> = {
  N: "North", NNE: "North-Northeast", NE: "Northeast", ENE: "East-Northeast",
  E: "East", ESE: "East-Southeast", SE: "Southeast", SSE: "South-Southeast",
  S: "South", SSW: "South-Southwest", SW: "Southwest", WSW: "West-Southwest",
  W: "West", WNW: "West-Northwest", NW: "Northwest", NNW: "North-Northwest",
}; // fmt: skip

const CONFIDENCE_TONE = { high: "green", medium: "amber", low: "red" } as const;

/** Real, measured roof-plane data for the pinned point — never a stand-in
 *  for the eventual full analysis, just an early, honest read so the
 *  customer can see they've pinned the right roof (and the right roof
 *  PLANE, on a multi-pitch building) before continuing. Distinct on
 *  purpose from the map's own camera tilt: everything shown here comes
 *  from Building Insights' measured roofSegmentStats, never the viewport. */
function RoofPitchCard({
  isLoading,
  isError,
  pitch,
}: {
  isLoading: boolean;
  isError: boolean;
  pitch: RoofPitchResult | null | undefined;
}) {
  if (isLoading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2.5 text-xs text-ink-soft"
      >
        <Loader2 size={14} className="animate-spin shrink-0" aria-hidden="true" />
        Reading the roof&apos;s real elevation data at this point…
      </motion.div>
    );
  }

  if (isError || !pitch) {
    return (
      <motion.p
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start gap-1.5 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2.5 text-xs leading-relaxed text-ink-soft"
      >
        <TriangleAlert size={13} strokeWidth={1.75} className="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
        No measured roof pitch is available for this exact point yet — this is only an early
        read; the full analysis after you confirm the boundary is unaffected.
      </motion.p>
    );
  }

  const planeLabel = pitch.segmentCount > 1 ? `Plane ${String.fromCharCode(65 + pitch.segmentIndex)}` : "Whole roof";

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2 rounded-[var(--radius-app)] border border-line bg-surface px-3.5 py-3"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-faint">
          <Gauge size={13} strokeWidth={1.9} aria-hidden="true" /> Roof plane at your pin
        </p>
        <Badge tone={CONFIDENCE_TONE[pitch.confidence]}>{pitch.confidence} confidence</Badge>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
        <div>
          <dt className="text-[11px] text-ink-faint">Roof pitch</dt>
          <dd className="font-medium text-ink">{pitch.pitchDeg.toFixed(1)}°</dd>
        </div>
        <div>
          <dt className="text-[11px] text-ink-faint">Orientation</dt>
          <dd className="font-medium text-ink">
            {COMPASS_FULL_NAME[pitch.orientation] ?? pitch.orientation}
          </dd>
        </div>
        {pitch.planeHeightM != null && (
          <div>
            <dt className="text-[11px] text-ink-faint">Elevation</dt>
            <dd className="font-medium text-ink">{pitch.planeHeightM.toFixed(1)} m</dd>
          </div>
        )}
        <div>
          <dt className="text-[11px] text-ink-faint">Roof plane</dt>
          <dd className="font-medium text-ink">
            {planeLabel}
            {pitch.segmentCount > 1 ? ` of ${pitch.segmentCount}` : ""}
          </dd>
        </div>
      </dl>
      <p className="text-[11px] leading-relaxed text-ink-faint">
        Measured from real elevation data for this roof — not the map&apos;s own camera angle.
        {pitch.matchedBy === "tolerated_contains" &&
          " Your pin is within the roof matching tolerance, so we used this roof plane's data."}
        {pitch.matchedBy === "nearest" &&
          " Your pin sits just outside the nearest roof plane's own outline, so this is that plane's data."}
      </p>
    </motion.div>
  );
}

const fieldStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
};

export function StartCheckWizard() {
  const router = useRouter();
  const createCheck = useCreateCheck();
  const { t } = useT();

  const STEPS: WizardStepMeta[] = STEP_META.map(({ key, labelKey, labelFallback }) => ({
    key,
    label: t(labelKey, labelFallback),
  }));

  const [step, setStep] = useState<WizardStep>("locate");

  // Step 1 — Locate
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [searching, setSearching] = useState(false);
  const [locateNotice, setLocateNotice] = useState<string | null>(null);
  // Real roof-plane data for the pinned point — re-fetches automatically
  // whenever `coords` changes (pin drag, map tap, search, current
  // location), no explicit button needed. See RoofPitchCard/
  // useRoofPitchAtPoint's own docstrings for why this is a query, not a
  // mutation like BuildingSelector's crop-confirm use of the same endpoint.
  const roofPitchQuery = useRoofPitchAtPoint(coords);

  // Step 2 — Select Building (Crop or Freehand)
  const [selection, setSelection] = useState<BuildingSelectionResult | null>(null);

  // Step 3 — Adjust Boundary
  const [confirmedBoundary, setConfirmedBoundary] = useState<LatLngPoint[]>([]);

  // Step 5 — Review
  // FIN-03 — kWh is the PRIMARY value for solar sizing (never derive it
  // from a ₹ amount when the customer knows their units); the ₹ pair
  // stays supported as a fallback for anyone who only knows their bill
  // amount. One mode is active at a time — never sent mixed.
  const [billMode, setBillMode] = useState<"kwh" | "inr">("kwh");
  const [billLow, setBillLow] = useState("");
  const [billHigh, setBillHigh] = useState("");
  const [consumptionLow, setConsumptionLow] = useState("");
  const [consumptionHigh, setConsumptionHigh] = useState("");
  // USN-01 — electricity connection number, captured here instead of only
  // post-analysis (see UsnCaptureFlow.tsx's OCR-based path on the result
  // page, still available for anyone who'd rather scan a bill than type
  // this). Optional: a check without one still runs.
  const [usn, setUsn] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const currentIndex = STEPS.findIndex((s) => s.key === step);

  const relabelPin = async (lat: number, lng: number) => {
    const formatted = await reverseGeocode(lat, lng);
    setAddress(formatted ?? "Pinned location");
  };

  const handleSuggestionPicked = (found: GeocodeResult) => {
    setCoords(found);
    setLocateNotice(found.formatted ? `Found: ${found.formatted}` : null);
  };

  const handleSearch = async () => {
    const query = address.trim();
    if (!query) return;
    setSearching(true);
    setLocateNotice(null);
    try {
      const found = await geocodeAddress(query);
      setCoords(found);
      setAddress(found.formatted ?? query);
      setLocateNotice(found.formatted ? `Found: ${found.formatted}` : null);
    } catch (err) {
      setLocateNotice(
        err instanceof GeocodeUnavailableError
          ? "Address search isn't available right now. Use your current location, or tap the map to place your pin."
          : `Couldn't find "${query}". Try a different search, or tap the map instead.`
      );
    } finally {
      setSearching(false);
    }
  };

  const handleUseCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocateNotice("Your browser can't share a location. Tap the map to place your pin instead.");
      return;
    }
    setLocating(true);
    setLocateNotice(null);

    // Fire a fast network fix and a precise GPS fix at the same time: the
    // pin lands as soon as EITHER answers (network/cached fixes take ~1s on
    // a phone), and the GPS fix quietly refines it if it arrives more
    // accurate. Previously GPS was tried alone for 8s, then network for
    // another 15s — up to 23s of spinner before anything moved.
    let bestAccuracy = Infinity;
    let pending = 2;
    let finished = false;

    const applyPosition = (pos: GeolocationPosition) => {
      const { latitude, longitude, accuracy } = pos.coords;
      if (accuracy >= bestAccuracy) return;
      bestAccuracy = accuracy;
      setCoords({ lat: latitude, lng: longitude });
      void relabelPin(latitude, longitude); // label catches up; never blocks the pin
      setLocating(false);
      finished = true;
      // accuracy is a 1-sigma radius in metres; past ~150m the fix is
      // coarse (WiFi/cell-tower) and may land a street from the roof.
      setLocateNotice(
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
        setLocateNotice("Location permission denied. Tap the map to place your pin instead.");
        return;
      }
      if (pending === 0) {
        setLocating(false);
        setLocateNotice("Couldn't get your location. Tap the map to place your pin instead.");
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

  const handleMapTap = (lat: number, lng: number) => {
    setCoords({ lat, lng });
    setLocateNotice(null);
    void relabelPin(lat, lng);
  };

  const handleBuildingSelected = (result: BuildingSelectionResult) => {
    setSelection(result);
    setStep("adjust-boundary");
  };

  const handleBoundaryAdjusted = (points: LatLngPoint[]) => {
    setConfirmedBoundary(points);
    setStep("confirm-building");
  };

  const handleChangeBuilding = () => {
    setSelection(null);
    setConfirmedBoundary([]);
    setStep("select-building");
  };

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

  // Mirrors backend providers/usn_ocr.py::_USN_FORMAT — a placeholder
  // length/charset check (no real jurisdiction format spec exists yet),
  // kept for immediate feedback rather than a round-trip 422. The
  // backend is still the source of truth: this is duplicated intentionally
  // as a client-side convenience, not the authoritative rule.
  const usnError = (() => {
    if (!usn.trim()) return null;
    return /^[A-Z0-9-]{6,20}$/.test(usn.trim().toUpperCase())
      ? null
      : "6-20 letters, numbers, or hyphens.";
  })();

  const handleStartAnalysis = async () => {
    if (!coords || !selection || confirmedBoundary.length < 3 || usnError) return;
    setSubmitError(null);
    try {
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
        confirmedBoundary,
        mapMetadata: {
          zoom: WIZARD_MAP_ZOOM,
          mapTypeId: "satellite",
          clickedLat: selection.centroid.lat,
          clickedLng: selection.centroid.lng,
          selectionMethod: selection.method,
        },
        ...consumptionInput,
        ...(usn.trim() ? { usn: usn.trim().toUpperCase() } : {}),
      });
      router.push(`/check/${check.id}/processing`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Couldn't start the check. Please try again.");
    }
  };

  return (
    <div className="flex h-[calc(100dvh-176px-env(safe-area-inset-bottom))] flex-col overflow-hidden md:h-[100dvh]">
      <div
        className="relative z-20 shrink-0 border-b border-line px-4 py-3 shadow-sm sm:px-6"
        style={{ backgroundColor: "var(--paper)" }}
      >
        <StepIndicator steps={STEPS} currentIndex={currentIndex} />
      </div>

      <div className="relative z-0 flex-1 overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          {step === "locate" && (
            <motion.div
              key="locate"
              variants={stepVariants}
              initial="hidden"
              animate="show"
              exit="exit"
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="mx-auto flex h-full max-w-xl flex-col gap-4 overflow-y-auto p-4 sm:p-6"
            >
              <motion.div variants={fieldStagger} initial="hidden" animate="show" className="flex flex-col gap-4">
                <motion.div variants={stepVariants} className="flex items-start gap-3">
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
                    style={{ background: "var(--good-bg)", color: "var(--brand)" }}
                    aria-hidden="true"
                  >
                    <Compass size={18} strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0">
                    <h1 className="text-lg font-semibold text-ink">
                      {t("wizard.step1Title", "Where's your rooftop?")}
                    </h1>
                    <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                      {t(
                        "wizard.step1Subtitle",
                        "Search for your address, use your current location, or tap the map to drop a pin."
                      )}
                    </p>
                  </div>
                </motion.div>

                <motion.div variants={stepVariants} className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <AddressAutocomplete
                      value={address}
                      onValueChange={setAddress}
                      onSelect={handleSuggestionPicked}
                      onUnavailable={setLocateNotice}
                      disabled={createCheck.isPending}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    className="h-11 w-11 shrink-0 !px-0"
                    onClick={handleSearch}
                    disabled={searching || !address.trim()}
                    aria-label="Search address"
                  >
                    {searching ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Search size={16} strokeWidth={1.75} aria-hidden="true" />}
                  </Button>
                </motion.div>

                <motion.button
                  variants={stepVariants}
                  type="button"
                  onClick={handleUseCurrentLocation}
                  disabled={locating}
                  className="flex min-h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-paper px-3 py-2.5 text-sm font-medium text-blue outline-none transition-colors hover:border-blue hover:bg-surface disabled:opacity-60"
                >
                  {locating ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Crosshair size={15} strokeWidth={1.75} aria-hidden="true" />}
                  {locating ? t("wizard.findingYou", "Finding you…") : t("wizard.useCurrentLocation", "Use my current location")}
                </motion.button>

                {locateNotice && (
                  <motion.p
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-ink-soft"
                    role="status"
                  >
                    {locateNotice}
                  </motion.p>
                )}

                <motion.div variants={stepVariants} className="min-h-[220px] flex-1 overflow-hidden rounded-[var(--radius-app)]">
                  <MapView
                    pins={coords ? [{ id: "pin", lat: coords.lat, lng: coords.lng, label: address.trim() || "Your pin" }] : []}
                    center={coords}
                    height={280}
                    interactive
                    onMove={handleMapTap}
                  />
                </motion.div>

                {coords && (
                  <RoofPitchCard
                    isLoading={roofPitchQuery.isLoading}
                    isError={roofPitchQuery.isError}
                    pitch={roofPitchQuery.data?.roofPitch}
                  />
                )}
              </motion.div>

              <div className="sticky bottom-0 -mx-4 mt-auto border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
                <Button
                  type="button"
                  size="md"
                  className="min-h-11 w-full"
                  onClick={() => coords && setStep("select-building")}
                  disabled={!coords}
                >
                  {coords
                    ? t("wizard.continueSelectBuilding", "Continue to select building")
                    : t("wizard.placePinFirst", "Place your pin first")}
                </Button>
              </div>
            </motion.div>
          )}

          {step === "select-building" && coords && (
            <motion.div
              key="select-building"
              variants={stepVariants}
              initial="hidden"
              animate="show"
              exit="exit"
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="h-full"
            >
              <BuildingSelector center={coords} onConfirm={handleBuildingSelected} />
            </motion.div>
          )}

          {step === "adjust-boundary" && selection && (
            <motion.div
              key="adjust-boundary"
              variants={stepVariants}
              initial="hidden"
              animate="show"
              exit="exit"
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="h-full"
            >
              <RoofCropEditor
                center={selection.centroid}
                initial={selection.points}
                onConfirm={handleBoundaryAdjusted}
                resetLabel={selection.method === "freehand" ? "Reset to my trace" : "Reset to my crop"}
                notice={
                  selection.usedFallback
                    ? "No building was detected inside your crop — adjust these corners to match your actual roof."
                    : undefined
                }
              />
            </motion.div>
          )}

          {step === "confirm-building" && selection && confirmedBoundary.length >= 3 && (
            <motion.div
              key="confirm-building"
              variants={stepVariants}
              initial="hidden"
              animate="show"
              exit="exit"
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="h-full"
            >
              <BuildingConfirmationPanel
                address={address}
                method={selection.method}
                // Recomputed from confirmedBoundary — the customer's own
                // edited corners — never selection.centroid, which is
                // stale as soon as "Adjust boundary" changes the shape.
                // See lib/geo/area.ts::polygonCentroid()'s docstring.
                centroid={polygonCentroid(confirmedBoundary)}
                boundary={confirmedBoundary}
                onConfirm={() => setStep("review")}
                onEditSelection={() => setStep("adjust-boundary")}
                onChangeBuilding={handleChangeBuilding}
              />
            </motion.div>
          )}

          {step === "review" && (
            <motion.div
              key="review"
              variants={stepVariants}
              initial="hidden"
              animate="show"
              exit="exit"
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="mx-auto flex h-full max-w-xl flex-col overflow-y-auto p-4 sm:p-6"
            >
              <motion.div variants={fieldStagger} initial="hidden" animate="show" className="flex flex-1 flex-col gap-4">
                <motion.div variants={stepVariants} className="flex items-start gap-3">
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
                    style={{ background: "var(--surface-2)", color: "var(--blue)" }}
                    aria-hidden="true"
                  >
                    <ClipboardCheck size={18} strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0">
                    <h1 className="text-lg font-semibold text-ink">{t("wizard.reviewTitle", "Review & start")}</h1>
                    <p className="mt-1 flex flex-wrap items-center gap-1 text-sm leading-relaxed text-ink-soft">
                      <MapPinned size={13} strokeWidth={1.75} className="shrink-0 text-ink-faint" aria-hidden="true" />
                      <span className="break-words">
                        {address.trim() || "Your pinned location"} · {confirmedBoundary.length} roof corners confirmed
                        {selection?.method === "freehand" ? " (hand-traced)" : " (crop-located)"}.
                      </span>
                    </p>
                  </div>
                </motion.div>

                <motion.div variants={stepVariants}>
                  <Card className="p-4 transition-shadow duration-200 focus-within:shadow-[var(--shadow-float)]">
                    <p className="mb-1.5 text-sm font-medium text-ink">{t("wizard.billCardTitle", "Your electricity usage")}</p>
                    <p className="mb-2 text-xs leading-relaxed text-ink-soft">
                      Optional — your lowest and highest month helps us size the system to what you actually use.
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
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="min-w-0 flex-1">
                          <label htmlFor="wizard-consumption-low" className="mb-1 block text-xs text-ink-faint">
                            Lowest month
                          </label>
                          <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2 transition-colors focus-within:border-blue">
                            <input
                              id="wizard-consumption-low"
                              type="number"
                              inputMode="numeric"
                              min={1}
                              value={consumptionLow}
                              onChange={(e) => setConsumptionLow(e.target.value)}
                              placeholder="400"
                              className="w-full min-w-0 bg-transparent text-sm text-ink outline-none"
                            />
                            <span className="text-sm text-ink-faint">kWh</span>
                          </div>
                        </div>
                        <div className="min-w-0 flex-1">
                          <label htmlFor="wizard-consumption-high" className="mb-1 block text-xs text-ink-faint">
                            Highest month
                          </label>
                          <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2 transition-colors focus-within:border-blue">
                            <input
                              id="wizard-consumption-high"
                              type="number"
                              inputMode="numeric"
                              min={1}
                              value={consumptionHigh}
                              onChange={(e) => setConsumptionHigh(e.target.value)}
                              placeholder="900"
                              className="w-full min-w-0 bg-transparent text-sm text-ink outline-none"
                            />
                            <span className="text-sm text-ink-faint">kWh</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="min-w-0 flex-1">
                          <label htmlFor="wizard-bill-low" className="mb-1 block text-xs text-ink-faint">
                            Lowest month
                          </label>
                          <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2 transition-colors focus-within:border-blue">
                            <span className="text-sm text-ink-faint">₹</span>
                            <input
                              id="wizard-bill-low"
                              type="number"
                              inputMode="numeric"
                              min={1}
                              value={billLow}
                              onChange={(e) => setBillLow(e.target.value)}
                              placeholder="1,200"
                              className="w-full min-w-0 bg-transparent text-sm text-ink outline-none"
                            />
                          </div>
                        </div>
                        <div className="min-w-0 flex-1">
                          <label htmlFor="wizard-bill-high" className="mb-1 block text-xs text-ink-faint">
                            Highest month
                          </label>
                          <div className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2 transition-colors focus-within:border-blue">
                            <span className="text-sm text-ink-faint">₹</span>
                            <input
                              id="wizard-bill-high"
                              type="number"
                              inputMode="numeric"
                              min={1}
                              value={billHigh}
                              onChange={(e) => setBillHigh(e.target.value)}
                              placeholder="2,400"
                              className="w-full min-w-0 bg-transparent text-sm text-ink outline-none"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                    <p className="mt-1.5 text-xs" style={billError ? { color: "var(--bad)" } : undefined}>
                      <span className={billError ? "" : "text-ink-faint"}>
                        {billError ?? "Optional — skip it and we'll size by roof space alone."}
                      </span>
                    </p>
                  </Card>
                </motion.div>

                <motion.div variants={stepVariants}>
                  <Card className="p-4 transition-shadow duration-200 focus-within:shadow-[var(--shadow-float)]">
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <IdCard size={15} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />
                      <p className="text-sm font-medium text-ink">
                        {t("wizard.usnCardTitle", "Electricity connection number (USN)")}
                      </p>
                    </div>
                    <p className="mb-3 text-xs leading-relaxed text-ink-soft">
                      Optional — find it on your electricity bill. You can also skip this and scan your
                      bill after your results are ready.
                    </p>
                    <label htmlFor="wizard-usn" className="sr-only">
                      Electricity connection number
                    </label>
                    <input
                      id="wizard-usn"
                      type="text"
                      value={usn}
                      onChange={(e) => setUsn(e.target.value.toUpperCase())}
                      placeholder="e.g. USN123456789"
                      maxLength={20}
                      className="min-h-11 w-full rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-2 font-mono text-sm uppercase tracking-wide text-ink outline-none transition-colors focus:border-blue"
                      style={usnError ? { borderColor: "var(--bad)" } : undefined}
                    />
                    <p className="mt-1.5 text-xs" style={usnError ? { color: "var(--bad)" } : undefined}>
                      <span className={usnError ? "" : "text-ink-faint"}>
                        {usnError ?? "Optional — skip it and confirm it later instead."}
                      </span>
                    </p>
                  </Card>
                </motion.div>

                {submitError && (
                  <motion.p
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-[var(--radius-app)] border px-3 py-2 text-xs leading-relaxed"
                    role="alert"
                    style={{ borderColor: "var(--bad)", color: "var(--bad)" }}
                  >
                    {submitError}
                  </motion.p>
                )}
              </motion.div>

              <div className="sticky bottom-0 -mx-4 mt-4 flex flex-col gap-2 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur-sm sm:static sm:mx-0 sm:mt-6 sm:flex-row sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
                <Button
                  type="button"
                  variant="secondary"
                  className="min-h-11 flex-1"
                  onClick={() => setStep("confirm-building")}
                  disabled={createCheck.isPending}
                >
                  {t("wizard.back", "Back")}
                </Button>
                <Button
                  type="button"
                  size="md"
                  className="min-h-11 flex-1"
                  onClick={handleStartAnalysis}
                  disabled={createCheck.isPending || !!billError || !!usnError}
                >
                  {createCheck.isPending ? t("wizard.starting", "Starting…") : t("wizard.startAnalysis", "Start solar analysis")}
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
