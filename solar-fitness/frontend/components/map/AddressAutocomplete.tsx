"use client";

// Address search with live suggestions, for the customer check form.
//
// Replaces "type the whole thing, press Search, hope": that path geocoded
// whatever was in the box and took the first result, so "a1" came back
// confidently as Golconda Fort and the customer got pinned to a monument.
// Suggestions let them see and choose the actual place.
//
// Every suggestion comes from Google Places via our own backend. Nothing
// is cached, seeded or invented here — an empty response renders an empty
// list.

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Search } from "lucide-react";
import {
  type AddressSuggestion,
  newSessionToken,
  resolveSuggestion,
  suggestAddresses,
  type GeocodeResult,
} from "@/lib/maps/geocode";

// Long enough that a fast typist does not fire a request per letter,
// short enough that the list feels live.
const DEBOUNCE_MS = 250;
// One or two letters match half the country; the suggestions are noise
// and each one is billable.
const MIN_QUERY_LENGTH = 3;

export function AddressAutocomplete({
  value,
  onValueChange,
  onSelect,
  onUnavailable,
  disabled = false,
}: {
  value: string;
  onValueChange: (value: string) => void;
  onSelect: (result: GeocodeResult) => void;
  /** Search is down or unconfigured — the caller tells the user to pin by hand. */
  onUnavailable: (message: string) => void;
  disabled?: boolean;
}) {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  // Whether the user has actively closed the list (Escape, a click away,
  // or a selection). `open` is DERIVED from this and the results, rather
  // than stored: keeping a separate open flag meant clearing it
  // synchronously inside the fetch effect, which cascades renders.
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);

  const session = useRef<string | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  // Set while a selection is being applied, so the value change it causes
  // does not immediately re-open the dropdown it just closed.
  const justPicked = useRef(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const open = !dismissed && suggestions.length > 0;

  // Clearing happens here, in an event handler, rather than in the fetch
  // effect — a short query should drop the list immediately, and an
  // effect cannot do that without a cascading render.
  const handleChange = (next: string) => {
    onValueChange(next);
    setDismissed(false);
    if (next.trim().length < MIN_QUERY_LENGTH) setSuggestions([]);
  };

  // Debounced fetch. Each keystroke cancels the previous request, so a
  // slow early response can never overwrite a newer one.
  useEffect(() => {
    if (justPicked.current) {
      justPicked.current = false;
      return;
    }
    const query = value.trim();
    if (query.length < MIN_QUERY_LENGTH) return;

    const timer = setTimeout(async () => {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      session.current ??= newSessionToken();
      setLoading(true);
      try {
        const found = await suggestAddresses(query, session.current, controller.signal);
        if (controller.signal.aborted) return;
        setSuggestions(found);
        setHighlighted(-1);
      } catch (err) {
        if (controller.signal.aborted || (err as Error)?.name === "AbortError") return;
        // A failing dropdown must not shout on every keystroke — it just
        // shows nothing, and the caller's own notice explains why.
        setSuggestions([]);
        onUnavailable(
          "Address search isn't available right now. Use your current location, or tap the map to place your pin."
        );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [value, onUnavailable]);

  // Close when the user clicks away, rather than trapping the dropdown open.
  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setDismissed(true);
    };
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, []);

  const pick = useCallback(
    async (suggestion: AddressSuggestion) => {
      justPicked.current = true;
      setDismissed(true);
      setSuggestions([]);
      onValueChange(suggestion.description);
      setResolving(true);
      try {
        const point = await resolveSuggestion(suggestion.placeId, session.current ?? undefined);
        onSelect(point);
      } catch {
        onUnavailable("We couldn't place that address. Tap the map to set your pin instead.");
      } finally {
        // The session ends with the selection; the next search starts a new one.
        session.current = null;
        setResolving(false);
      }
    },
    [onSelect, onUnavailable, onValueChange]
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((i) => (i + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      void pick(suggestions[highlighted]);
    } else if (event.key === "Escape") {
      setDismissed(true);
    }
  };

  const busy = loading || resolving;

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 focus-within:border-blue">
        {busy ? (
          <Loader2 size={15} strokeWidth={1.75} className="animate-spin text-ink-faint" aria-hidden="true" />
        ) : (
          <Search size={15} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />
        )}
        <input
          type="text"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setDismissed(false)}
          disabled={disabled || resolving}
          placeholder="Start typing your address or area"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-controls="address-suggestions"
          className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint disabled:opacity-60"
        />
      </div>

      {open && suggestions.length > 0 && (
        <ul
          id="address-suggestions"
          role="listbox"
          className="absolute z-20 mt-1 w-full overflow-hidden rounded-[var(--radius-app)] border border-line bg-paper shadow-[var(--shadow-float)]"
        >
          {suggestions.map((suggestion, index) => (
            <li key={suggestion.placeId} role="option" aria-selected={index === highlighted}>
              <button
                type="button"
                // onMouseDown, not onClick: the input's blur fires first
                // otherwise and closes the list before the click lands.
                onMouseDown={(e) => {
                  e.preventDefault();
                  void pick(suggestion);
                }}
                onMouseEnter={() => setHighlighted(index)}
                className={`flex w-full items-start gap-2 px-3 py-2 text-left text-sm transition-colors ${
                  index === highlighted ? "bg-[var(--surface-2)] text-ink" : "text-ink-soft"
                }`}
              >
                <MapPin
                  size={14}
                  strokeWidth={1.75}
                  className="mt-0.5 shrink-0 text-ink-faint"
                  aria-hidden="true"
                />
                <span>{suggestion.description}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
