import type { Metadata } from "next";
import { StartCheckWizard } from "./StartCheckWizard";

export const metadata: Metadata = {
  title: "Start a solar check",
  robots: { index: false, follow: false },
};

export default function StartCheckPage() {
  return <StartCheckWizard />;
}
