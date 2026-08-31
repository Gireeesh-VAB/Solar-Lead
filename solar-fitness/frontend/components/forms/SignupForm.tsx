"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Primitives";

const schema = z.object({
  name: z.string().min(2, "Enter your name."),
  email: z.string().email("Enter a valid email address."),
  phone: z.string().min(7, "Enter a valid phone number."),
  password: z.string().min(6, "Password must be at least 6 characters."),
});
type FormValues = z.infer<typeof schema>;

export function SignupForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", phone: "", password: "" },
  });

  const onSubmit = handleSubmit(async () => {
    setSubmitting(true);
    await new Promise((r) => setTimeout(r, 500));
    router.push("/home");
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
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
          aria-describedby={errors.name ? "name-error" : undefined}
          {...register("name")}
        />
        {errors.name && (
          <p id="name-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
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
          aria-describedby={errors.email ? "email-error" : undefined}
          {...register("email")}
        />
        {errors.email && (
          <p id="email-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
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
          aria-describedby={errors.phone ? "phone-error" : undefined}
          {...register("phone")}
        />
        {errors.phone && (
          <p id="phone-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.phone.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id="password-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.password.message}
          </p>
        )}
      </div>
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? "Creating your account…" : "Create account"}
      </Button>
      <p className="text-center text-xs text-ink-faint">
        Demo build — this creates a mock account and signs you in against sample data.
      </p>
    </form>
  );
}
