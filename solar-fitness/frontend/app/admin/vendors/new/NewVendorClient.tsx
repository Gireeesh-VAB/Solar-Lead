"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, Copy } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { useCreateAdminVendor } from "@/lib/query/hooks";
import { ApiError } from "@/lib/api/fetchClient";
import type { NewVendorResult } from "@/lib/api/client";
import { optionalIndianPhone, sanitizePhoneInput } from "@/lib/validation/phone";

// max() on each optional field mirrors the backend's own VendorCreateRequest
// limits (routers/app_admin_vendors.py), which in turn mirror the VendorRow
// database columns — catching an oversized value here, inline, is friendlier
// than the round trip to the server's 422 (previously an unhandled 500: an
// oversized value hit Postgres's own varchar limit directly, with nothing at
// either layer validating first).
const schema = z.object({
  name: z.string().min(1, "Enter the vendor's display name.").max(255),
  legalName: z.string().max(255, "Too long — 255 characters max.").optional(),
  gstNumber: z.string().max(32, "Too long — 32 characters max.").optional(),
  panNumber: z.string().max(16, "Too long — 16 characters max.").optional(),
  contactName: z.string().max(255, "Too long — 255 characters max.").optional(),
  contactPhone: optionalIndianPhone,
  contactEmail: z.string().email("Enter a valid email address — this becomes the vendor's login.").max(255),
  addressLine1: z.string().max(255, "Too long — 255 characters max.").optional(),
  addressLine2: z.string().max(255, "Too long — 255 characters max.").optional(),
  city: z.string().max(128, "Too long — 128 characters max.").optional(),
  state: z.string().max(128, "Too long — 128 characters max.").optional(),
  pincode: z.string().max(16, "Too long — 16 characters max.").optional(),
  serviceAreaRegion: z.string().min(1, "Enter a service area region."),
  serviceAreaDistricts: z.string().optional(),
  payoutMethodType: z.enum(["UPI", "Bank transfer"]),
  payoutMaskedAccount: z.string().min(1, "Enter a payout account identifier."),
  certifications: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

const inputClass =
  "w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue";
const labelClass = "mb-1 block text-sm font-medium text-ink";
const errorClass = "mt-1 text-xs";

function splitList(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function NewVendorClient() {
  const createVendor = useCreateAdminVendor();
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<NewVendorResult | null>(null);
  const [copied, setCopied] = useState(false);
  const {
    register,
    handleSubmit,
    trigger,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      contactEmail: "",
      serviceAreaRegion: "",
      payoutMethodType: "UPI",
      payoutMaskedAccount: "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const created = await createVendor.mutateAsync({
        name: values.name,
        legalName: values.legalName || undefined,
        gstNumber: values.gstNumber || undefined,
        panNumber: values.panNumber || undefined,
        contactName: values.contactName || undefined,
        contactPhone: values.contactPhone || undefined,
        contactEmail: values.contactEmail,
        addressLine1: values.addressLine1 || undefined,
        addressLine2: values.addressLine2 || undefined,
        city: values.city || undefined,
        state: values.state || undefined,
        pincode: values.pincode || undefined,
        serviceAreaRegion: values.serviceAreaRegion,
        serviceAreaDistricts: splitList(values.serviceAreaDistricts),
        payoutMethodType: values.payoutMethodType,
        payoutMaskedAccount: values.payoutMaskedAccount,
        certifications: splitList(values.certifications),
        documents: [],
      });
      setResult(created);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    }
  });

  if (result) {
    return (
      <Card className="max-w-lg space-y-4 p-5">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-medium" style={{ color: "var(--good)" }}>
            <Check size={16} strokeWidth={1.75} /> {result.vendor.name} was created
          </p>
          <p className="mt-1 text-sm text-ink-soft">
            Share this login with the vendor now — the temporary password won&apos;t be shown again.
          </p>
        </div>
        <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-surface p-3">
          <div>
            <p className="text-xs text-ink-faint">Login email</p>
            <p className="font-mono tabular text-sm text-ink">{result.loginEmail}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Temporary password</p>
            <div className="flex items-center gap-2">
              <p className="font-mono tabular text-sm text-ink">{result.temporaryPassword}</p>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard?.writeText(result.temporaryPassword);
                  setCopied(true);
                }}
                className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-ink"
              >
                <Copy size={12} strokeWidth={1.75} /> {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Link href={`/admin/vendors/${result.vendor.id}`}>
            <Button size="sm">View vendor</Button>
          </Link>
          <Link href="/admin/vendors">
            <Button size="sm" variant="secondary">
              Back to vendors
            </Button>
          </Link>
        </div>
      </Card>
    );
  }

  return (
    <form onSubmit={onSubmit} className="max-w-2xl space-y-6" noValidate>
      <Card className="space-y-4 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Business identity</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="name" className={labelClass}>
              Display name
            </label>
            <input id="name" className={inputClass} aria-invalid={!!errors.name} {...register("name")} />
            {errors.name && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.name.message}</p>}
          </div>
          <div>
            <label htmlFor="legalName" className={labelClass}>
              Legal / registered name
            </label>
            <input id="legalName" className={inputClass} aria-invalid={!!errors.legalName} {...register("legalName")} />
            {errors.legalName && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.legalName.message}</p>}
          </div>
          <div>
            <label htmlFor="gstNumber" className={labelClass}>
              GST number
            </label>
            <input id="gstNumber" className={inputClass} aria-invalid={!!errors.gstNumber} {...register("gstNumber")} />
            {errors.gstNumber && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.gstNumber.message}</p>}
          </div>
          <div>
            <label htmlFor="panNumber" className={labelClass}>
              PAN number
            </label>
            <input id="panNumber" className={inputClass} aria-invalid={!!errors.panNumber} {...register("panNumber")} />
            {errors.panNumber && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.panNumber.message}</p>}
          </div>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Contact & login</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="contactName" className={labelClass}>
              Contact person
            </label>
            <input id="contactName" className={inputClass} aria-invalid={!!errors.contactName} {...register("contactName")} />
            {errors.contactName && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.contactName.message}</p>}
          </div>
          <div>
            <label htmlFor="contactPhone" className={labelClass}>
              Contact phone
            </label>
            <input
              id="contactPhone"
              type="tel"
              inputMode="numeric"
              className={inputClass}
              aria-invalid={!!errors.contactPhone}
              {...register("contactPhone", {
                onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
                  e.target.value = sanitizePhoneInput(e.target.value);
                  void trigger("contactPhone");
                },
              })}
            />
            {errors.contactPhone && (
              <p className={errorClass} style={{ color: "var(--bad)" }}>
                {errors.contactPhone.message}
              </p>
            )}
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="contactEmail" className={labelClass}>
              Contact email (becomes login)
            </label>
            <input
              id="contactEmail"
              type="email"
              className={inputClass}
              aria-invalid={!!errors.contactEmail}
              {...register("contactEmail")}
            />
            {errors.contactEmail && (
              <p className={errorClass} style={{ color: "var(--bad)" }}>
                {errors.contactEmail.message}
              </p>
            )}
          </div>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Address</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label htmlFor="addressLine1" className={labelClass}>
              Address line 1
            </label>
            <input id="addressLine1" className={inputClass} aria-invalid={!!errors.addressLine1} {...register("addressLine1")} />
            {errors.addressLine1 && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.addressLine1.message}</p>}
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="addressLine2" className={labelClass}>
              Address line 2
            </label>
            <input id="addressLine2" className={inputClass} aria-invalid={!!errors.addressLine2} {...register("addressLine2")} />
            {errors.addressLine2 && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.addressLine2.message}</p>}
          </div>
          <div>
            <label htmlFor="city" className={labelClass}>
              City
            </label>
            <input id="city" className={inputClass} aria-invalid={!!errors.city} {...register("city")} />
            {errors.city && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.city.message}</p>}
          </div>
          <div>
            <label htmlFor="state" className={labelClass}>
              State
            </label>
            <input id="state" className={inputClass} aria-invalid={!!errors.state} {...register("state")} />
            {errors.state && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.state.message}</p>}
          </div>
          <div>
            <label htmlFor="pincode" className={labelClass}>
              Pincode
            </label>
            <input id="pincode" className={inputClass} aria-invalid={!!errors.pincode} {...register("pincode")} />
            {errors.pincode && <p className={errorClass} style={{ color: "var(--bad)" }}>{errors.pincode.message}</p>}
          </div>
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Service area & payout</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="serviceAreaRegion" className={labelClass}>
              Service area region
            </label>
            <input
              id="serviceAreaRegion"
              className={inputClass}
              aria-invalid={!!errors.serviceAreaRegion}
              {...register("serviceAreaRegion")}
            />
            {errors.serviceAreaRegion && (
              <p className={errorClass} style={{ color: "var(--bad)" }}>
                {errors.serviceAreaRegion.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="serviceAreaDistricts" className={labelClass}>
              Districts (comma-separated)
            </label>
            <input id="serviceAreaDistricts" className={inputClass} {...register("serviceAreaDistricts")} />
          </div>
          <div>
            <label htmlFor="payoutMethodType" className={labelClass}>
              Payout method
            </label>
            <select id="payoutMethodType" className={inputClass} {...register("payoutMethodType")}>
              <option value="UPI">UPI</option>
              <option value="Bank transfer">Bank transfer</option>
            </select>
          </div>
          <div>
            <label htmlFor="payoutMaskedAccount" className={labelClass}>
              Payout account (UPI ID or account number)
            </label>
            <input
              id="payoutMaskedAccount"
              className={inputClass}
              aria-invalid={!!errors.payoutMaskedAccount}
              {...register("payoutMaskedAccount")}
            />
            {errors.payoutMaskedAccount && (
              <p className={errorClass} style={{ color: "var(--bad)" }}>
                {errors.payoutMaskedAccount.message}
              </p>
            )}
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="certifications" className={labelClass}>
              Certifications (comma-separated)
            </label>
            <input id="certifications" className={inputClass} {...register("certifications")} />
          </div>
        </div>
      </Card>

      {formError && (
        <p role="alert" className="text-sm" style={{ color: "var(--bad)" }}>
          {formError}
        </p>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={createVendor.isPending}>
          {createVendor.isPending ? "Creating vendor…" : "Create vendor"}
        </Button>
        <Link href="/admin/vendors">
          <Button type="button" variant="secondary">
            Cancel
          </Button>
        </Link>
      </div>
    </form>
  );
}
