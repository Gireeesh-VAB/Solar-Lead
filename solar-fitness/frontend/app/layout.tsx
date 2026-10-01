import type { Metadata, Viewport } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query/provider";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://solar-fitness.example.com";

// viewportFit: "cover" lets content draw under the iPhone notch/Dynamic
// Island/home indicator (paired with the safe-area padding in globals.css
// and on the fixed Navigation bar) instead of Safari letterboxing behind
// a plain white bar. themeColor tints the Safari status bar/task switcher
// to match the app instead of leaving it default black/white.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f8f4" },
    { media: "(prefers-color-scheme: dark)", color: "#121815" },
  ],
};

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
  appleWebApp: {
    title: "GoHarit",
    statusBarStyle: "default",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <head>
        {/* Applies a stored Light/Dark theme choice before first paint —
            see lib/theme.ts's THEME_INIT_SCRIPT docstring for why this
            can't be a React effect. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
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
