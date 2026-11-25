"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { Check, Mail, User as UserIcon } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { useUpdateCustomerProfile } from "@/lib/query/hooks";
import type { CustomerProfile } from "@/lib/fixtures/customer";
import { requiredIndianPhone, sanitizePhoneInput } from "@/lib/validation/phone";

const schema = z.object({
  name: z.string().min(2, "Enter your name."),
  email: z.string().email("Enter a valid email address."),
  phone: requiredIndianPhone,
});
type FormValues = z.infer<typeof schema>;

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

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0]?.[0] ?? "").concat(parts.length > 1 ? parts[parts.length - 1][0] : "").toUpperCase();
}

const inputClass =
  "w-full min-h-[44px] rounded-[var(--radius-app)] border border-line bg-paper px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-blue";

export function ProfileForm({ profile }: { profile: CustomerProfile }) {
  const updateProfile = useUpdateCustomerProfile();
  const [notify, setNotify] = useState(profile.notifyOnComplete);
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
    trigger,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: profile.name, email: profile.email, phone: profile.phone },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSaved(false);
    await updateProfile.mutateAsync({ ...values, notifyOnComplete: notify });
    setSaved(true);
  });

  const toggleNotify = async () => {
    const next = !notify;
    setNotify(next);
    setSaved(false);
    await updateProfile.mutateAsync({ notifyOnComplete: next });
    setSaved(true);
  };

  return (
    <motion.div initial="hidden" animate="show" variants={stagger} className="flex flex-col gap-6">
      {/* ---------- Header ---------- */}
      <motion.div
        variants={fadeUp}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative isolate overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface px-5 py-8 text-center sm:px-8"
      >
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute -top-16 left-1/2 h-48 w-80 -translate-x-1/2 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--blue-soft), transparent 70%)", opacity: 0.35 }}
          />
        </div>
        <div
          className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full text-lg font-semibold text-white"
          style={{
            background: "linear-gradient(150deg, var(--blue), var(--teal))",
            boxShadow: "var(--shadow-float)",
          }}
          aria-hidden="true"
        >
          {initialsFor(profile.name)}
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{profile.name}</h1>
        <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-ink-soft">
          <Mail size={13} strokeWidth={1.75} aria-hidden="true" />
          {profile.email}
        </p>
      </motion.div>

      <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
        {/* ---------- Personal details ---------- */}
        <motion.div variants={fadeUp}>
          <Card className="space-y-5 p-5 sm:p-6">
            <div className="flex items-center gap-2">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--surface-2)", color: "var(--blue)" }}
                aria-hidden="true"
              >
                <UserIcon size={15} strokeWidth={1.75} />
              </span>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Personal details</h2>
            </div>

            <div>
              <label htmlFor="name" className="mb-1.5 block text-sm font-medium text-ink">
                Full name
              </label>
              <input
                id="name"
                type="text"
                autoComplete="name"
                className={inputClass}
                aria-invalid={!!errors.name}
                {...register("name")}
              />
              {errors.name && (
                <p className="mt-1.5 text-xs" style={{ color: "var(--bad)" }}>
                  {errors.name.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                className={inputClass}
                aria-invalid={!!errors.email}
                {...register("email")}
              />
              {errors.email && (
                <p className="mt-1.5 text-xs" style={{ color: "var(--bad)" }}>
                  {errors.email.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="phone" className="mb-1.5 block text-sm font-medium text-ink">
                Phone
              </label>
              <input
                id="phone"
                type="tel"
                inputMode="numeric"
                autoComplete="tel"
                className={inputClass}
                aria-invalid={!!errors.phone}
                {...register("phone", {
                  onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
                    e.target.value = sanitizePhoneInput(e.target.value);
                    void trigger("phone");
                  },
                })}
              />
              {errors.phone && (
                <p className="mt-1.5 text-xs" style={{ color: "var(--bad)" }}>
                  {errors.phone.message}
                </p>
              )}
            </div>
          </Card>
        </motion.div>

        {/* ---------- Notifications ---------- */}
        <motion.div variants={fadeUp}>
          <Card className="flex items-center justify-between gap-3 p-5 sm:p-6">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Email me when a check finishes</p>
              <p className="mt-0.5 text-xs text-ink-soft">We&apos;ll send your result as soon as it&apos;s ready.</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={notify}
              onClick={toggleNotify}
              className="relative h-[28px] w-[48px] shrink-0 rounded-full transition-colors"
              style={{ background: notify ? "var(--brand)" : "var(--surface-2)" }}
            >
              <span
                className="absolute top-[2px] h-[24px] w-[24px] rounded-full bg-white shadow transition-transform"
                style={{ transform: notify ? "translateX(22px)" : "translateX(2px)" }}
              />
            </button>
          </Card>
        </motion.div>

        {/* ---------- Save action ---------- */}
        <motion.div variants={fadeUp} className="flex flex-col items-stretch gap-2.5 border-t border-line pt-5 sm:flex-row sm:items-center">
          <Button type="submit" disabled={updateProfile.isPending} className="w-full min-h-[44px] sm:w-auto">
            {updateProfile.isPending ? "Saving…" : "Save changes"}
          </Button>
          {saved && !updateProfile.isPending && (
            <span className="flex items-center justify-center gap-1 text-xs sm:justify-start" style={{ color: "var(--good)" }}>
              <Check size={14} strokeWidth={1.75} aria-hidden="true" />
              Saved
            </span>
          )}
        </motion.div>
      </form>
    </motion.div>
  );
}
