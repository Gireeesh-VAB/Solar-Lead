"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { useUpdateCustomerProfile } from "@/lib/query/hooks";
import type { CustomerProfile } from "@/lib/fixtures/customer";

const schema = z.object({
  name: z.string().min(2, "Enter your name."),
  email: z.string().email("Enter a valid email address."),
  phone: z.string().min(7, "Enter a valid phone number."),
});
type FormValues = z.infer<typeof schema>;

export function ProfileForm({ profile }: { profile: CustomerProfile }) {
  const updateProfile = useUpdateCustomerProfile();
  const [notify, setNotify] = useState(profile.notifyOnComplete);
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
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
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <Card className="space-y-4 p-5">
        <div>
          <label htmlFor="name" className="mb-1 block text-sm font-medium text-ink">
            Full name
          </label>
          <input
            id="name"
            type="text"
            autoComplete="name"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
            aria-invalid={!!errors.name}
            {...register("name")}
          />
          {errors.name && (
            <p className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
              {errors.name.message}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
            aria-invalid={!!errors.email}
            {...register("email")}
          />
          {errors.email && (
            <p className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
              {errors.email.message}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="phone" className="mb-1 block text-sm font-medium text-ink">
            Phone
          </label>
          <input
            id="phone"
            type="tel"
            autoComplete="tel"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
            aria-invalid={!!errors.phone}
            {...register("phone")}
          />
          {errors.phone && (
            <p className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
              {errors.phone.message}
            </p>
          )}
        </div>
      </Card>

      <Card className="flex items-center justify-between gap-3 p-4">
        <div>
          <p className="text-sm font-medium text-ink">Email me when a check finishes</p>
          <p className="text-xs text-ink-soft">We&apos;ll send your result as soon as it&apos;s ready.</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={notify}
          onClick={toggleNotify}
          className="relative h-6 w-11 shrink-0 rounded-full transition-colors"
          style={{ background: notify ? "var(--amber)" : "var(--surface-2)" }}
        >
          <span
            className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
            style={{ transform: notify ? "translateX(22px)" : "translateX(2px)" }}
          />
        </button>
      </Card>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={updateProfile.isPending}>
          {updateProfile.isPending ? "Saving…" : "Save changes"}
        </Button>
        {saved && !updateProfile.isPending && (
          <span className="flex items-center gap-1 text-xs" style={{ color: "var(--good)" }}>
            <Check size={14} strokeWidth={1.75} aria-hidden="true" />
            Saved
          </span>
        )}
      </div>
    </form>
  );
}
