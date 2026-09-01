import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query/provider";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://solar-fitness.example.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Solar Site Fitness & Capacity Engine",
    template: "%s · Solar Site Fitness & Capacity Engine",
  },
  description:
    "Assess whether solar (rooftop or floating) can be installed at a candidate site, and at what capacity — verdict, capacity, confidence, and binding constraint in one view.",
  openGraph: {
    type: "website",
    siteName: "Solar Site Fitness & Capacity Engine",
    title: "Solar Site Fitness & Capacity Engine",
    description:
      "Assess whether solar (rooftop or floating) can be installed at a candidate site, and at what capacity.",
    url: SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: "Solar Site Fitness & Capacity Engine",
    description:
      "Assess whether solar (rooftop or floating) can be installed at a candidate site, and at what capacity.",
  },
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap"
        />
      </head>
      <body className="min-h-full flex flex-col bg-paper text-ink">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
