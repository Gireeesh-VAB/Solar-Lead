// Type declarations for Google's <model-viewer> custom element
// (@google/model-viewer). It's a plain custom element, not a React
// component, so JSX needs to be told it's a valid intrinsic tag —
// sibling to next-env.d.ts at the project root per this repo's only
// existing ambient-declaration file.
import type { DetailedHTMLProps, HTMLAttributes } from "react";

type ModelViewerAttributes = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string;
  alt?: string;
  poster?: string;
  ar?: boolean;
  "camera-controls"?: boolean;
  "auto-rotate"?: boolean;
  "auto-rotate-delay"?: number | string;
  "shadow-intensity"?: number | string;
  "shadow-softness"?: number | string;
  "camera-orbit"?: string;
  "field-of-view"?: string;
  "min-camera-orbit"?: string;
  "max-camera-orbit"?: string;
  "interaction-prompt"?: string;
  "disable-zoom"?: boolean;
  exposure?: number | string;
  loading?: "auto" | "lazy" | "eager";
  reveal?: "auto" | "interaction" | "manual";
  "environment-image"?: string;
};

// React 19's @types/react declares JSX.IntrinsicElements under the
// `React.JSX` namespace (not the bare global `JSX` namespace), so that's
// what needs augmenting for the new jsx: "react-jsx" transform to see
// this tag as valid.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": ModelViewerAttributes;
    }
  }
}

export {};
