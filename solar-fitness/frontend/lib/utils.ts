import type { ConstraintKind, Verdict } from "@/lib/types";

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function formatKwp(value: number): string {
  return `${value.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWp`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  SUITABLE: "Suitable",
  SUITABLE_SUBJECT_TO_SURVEY: "Suitable, subject to survey",
  CONDITIONAL: "Conditional",
  INSUFFICIENT_DATA: "Insufficient data",
  NOT_SUITABLE: "Not suitable",
};

export const CONSTRAINT_KIND_LABEL: Record<ConstraintKind, string> = {
  physical: "Physical",
  regulatory: "Regulatory",
  commercial: "Commercial",
};

export function siteTypeLabel(type: string): string {
  switch (type) {
    case "ROOFTOP_GOVT":
      return "Rooftop — Government";
    case "ROOFTOP_RESIDENTIAL":
      return "Rooftop — Residential";
    case "ROOFTOP_CI":
      return "Rooftop — Commercial & Industrial";
    case "FLOATING":
      return "Floating";
    default:
      return type;
  }
}
