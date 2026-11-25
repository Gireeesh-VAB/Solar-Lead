"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { motion } from "framer-motion";
import {
  MapPin,
  Star,
  Shield,
  Award,
  Phone,
  ChevronRight,
  Search,
  Building2,
  Users,
  Zap,
} from "lucide-react";
import { useScrollReveal } from "@/lib/hooks/useScrollReveal";

// Scroll-reveal for a single vendor card — file-local since useScrollReveal
// is a hook and can't be called inside the vendors.map() callback below.
function RevealCard({
  delay,
  className,
  children,
}: {
  delay: number;
  className?: string;
  children: ReactNode;
}) {
  const { ref, inView } = useScrollReveal("-60px");
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      transition={{ duration: 0.4, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

const vendors = [
  {
    id: 1,
    name: "SunPower Solutions",
    rating: 4.9,
    reviews: 342,
    premium: true,
    yearsInBusiness: 15,
    installations: "5,000+",
    specialties: ["Residential", "Commercial"],
    initials: "SP",
  },
  {
    id: 2,
    name: "GreenTech Solar",
    rating: 4.8,
    reviews: 289,
    premium: true,
    yearsInBusiness: 12,
    installations: "3,500+",
    specialties: ["Residential", "Battery storage"],
    initials: "GT",
  },
  {
    id: 3,
    name: "EcoSun Energy",
    rating: 4.7,
    reviews: 198,
    premium: false,
    yearsInBusiness: 8,
    installations: "2,200+",
    specialties: ["Residential", "EV charging"],
    initials: "ES",
  },
  {
    id: 4,
    name: "Bright Future Solar",
    rating: 4.8,
    reviews: 256,
    premium: true,
    yearsInBusiness: 10,
    installations: "4,100+",
    specialties: ["Commercial", "Industrial"],
    initials: "BF",
  },
  {
    id: 5,
    name: "CleanEnergy Pro",
    rating: 4.6,
    reviews: 178,
    premium: false,
    yearsInBusiness: 6,
    installations: "1,800+",
    specialties: ["Residential", "Small business"],
    initials: "CE",
  },
  {
    id: 6,
    name: "SolarMax Systems",
    rating: 4.9,
    reviews: 312,
    premium: true,
    yearsInBusiness: 14,
    installations: "4,800+",
    specialties: ["All types", "Maintenance"],
    initials: "SM",
  },
];

const stats = [
  { icon: Building2, value: "500+", label: "Verified vendors" },
  { icon: Users, value: "50K+", label: "Happy customers" },
  { icon: Zap, value: "100MW+", label: "Installed capacity" },
  { icon: Award, value: "4.8", label: "Average rating" },
];

export default function VendorsSection() {
  const [searchLocation, setSearchLocation] = useState("");
  const { ref: headerRef, inView: headerInView } = useScrollReveal("-80px");

  function handleSearch(e: FormEvent) {
    e.preventDefault();
  }

  return (
    <section id="vendors" className="bg-paper py-20 lg:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <motion.div
          ref={headerRef}
          initial={{ opacity: 0, y: 16 }}
          animate={headerInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.5 }}
          className="mx-auto mb-12 max-w-2xl text-center"
        >
          <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-good-bg px-4 py-1.5 text-sm font-medium text-good">
            <Building2 className="h-4 w-4" />
            Trusted partners
          </div>
          <h2 className="mb-4 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Top solar vendors in <span className="gradient-text">your area</span>
          </h2>
          <p className="mb-8 text-lg text-ink-soft">
            Connect with certified, top-rated solar installers ready to bring clean
            energy to your home.
          </p>

          <form onSubmit={handleSearch} className="mx-auto max-w-md">
            <div className="relative">
              <MapPin className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-faint" />
              <input
                type="text"
                value={searchLocation}
                onChange={(e) => setSearchLocation(e.target.value)}
                placeholder="Enter your city or zip code"
                className="w-full rounded-2xl border border-line bg-surface py-3.5 pl-12 pr-12 text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-brand"
              />
              <button
                type="submit"
                aria-label="Search vendors"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-brand p-2 text-white transition-colors hover:bg-brand-soft"
              >
                <Search className="h-5 w-5" />
              </button>
            </div>
          </form>
        </motion.div>

        <div className="mb-12 grid grid-cols-2 gap-4 md:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-line bg-surface p-5 text-center">
              <stat.icon className="mx-auto mb-2 h-7 w-7 text-brand" strokeWidth={1.75} />
              <p className="text-2xl font-bold text-ink">{stat.value}</p>
              <p className="text-sm text-ink-soft">{stat.label}</p>
            </div>
          ))}
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {vendors.map((vendor, index) => (
            <RevealCard
              key={vendor.id}
              delay={(index % 3) * 0.08}
              className="group relative rounded-2xl border border-line bg-surface p-6 transition-colors hover:border-brand-soft/40"
            >
              {vendor.premium && (
                <div className="absolute right-5 top-5 inline-flex items-center gap-1 rounded-full bg-amber-soft/20 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-warn">
                  <Award className="h-3 w-3" />
                  Premium
                </div>
              )}

              <div className="mb-4 flex items-start gap-4">
                <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl bg-brand text-lg font-bold text-white">
                  {vendor.initials}
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-ink">{vendor.name}</h3>
                  <div className="mt-1 flex items-center gap-2 text-sm">
                    <span className="inline-flex items-center gap-1 font-semibold text-ink">
                      <Star className="h-3.5 w-3.5 fill-current text-amber" />
                      {vendor.rating}
                    </span>
                    <span className="text-ink-faint">·</span>
                    <span className="text-ink-soft">{vendor.reviews} reviews</span>
                  </div>
                </div>
              </div>

              <div className="mb-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-surface-2 p-3">
                  <p className="text-xs text-ink-faint">Experience</p>
                  <p className="font-semibold text-ink">{vendor.yearsInBusiness} years</p>
                </div>
                <div className="rounded-xl bg-surface-2 p-3">
                  <p className="text-xs text-ink-faint">Installations</p>
                  <p className="font-semibold text-ink">{vendor.installations}</p>
                </div>
              </div>

              <div className="mb-4 flex flex-wrap gap-2">
                {vendor.specialties.map((specialty) => (
                  <span
                    key={specialty}
                    className="rounded-full bg-good-bg px-3 py-1 text-xs font-medium text-good"
                  >
                    {specialty}
                  </span>
                ))}
              </div>

              <div className="mb-4 flex items-center gap-2 text-sm font-medium text-good">
                <Shield className="h-4 w-4" />
                Verified partner
              </div>

              <div className="flex gap-3">
                <button
                  type="button"
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-soft"
                >
                  Get quote
                  <ChevronRight className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label={`Call ${vendor.name}`}
                  className="rounded-xl border border-line p-2.5 text-ink-soft transition-colors hover:border-brand-soft/40 hover:text-brand"
                >
                  <Phone className="h-5 w-5" />
                </button>
              </div>
            </RevealCard>
          ))}
        </div>

        <div className="mt-12 text-center">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full border border-brand-soft/40 px-8 py-3.5 font-semibold text-brand transition-colors hover:bg-good-bg"
          >
            View all vendors
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </section>
  );
}
