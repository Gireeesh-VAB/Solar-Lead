// Shared Indian mobile number validation — one regex and one error
// message so signup, profile, and admin's new-vendor form all reject
// (and explain) bad numbers the same way, matching the backend's own
// IndianMobile validator in routers/common.py.

import { z } from "zod";

export const INDIAN_MOBILE_REGEX = /^[6-9]\d{9}$/;
export const PHONE_ERROR_MESSAGE = "Please enter a valid 10-digit mobile number.";

/** A phone number the form requires (signup, profile). Leading/trailing
 *  whitespace is trimmed before the shape check runs. */
export const requiredIndianPhone = z.string().trim().regex(INDIAN_MOBILE_REGEX, PHONE_ERROR_MESSAGE);

/** A phone number the form allows to be left blank (admin's new-vendor
 *  contact phone), but must be a valid Indian mobile if provided. */
export const optionalIndianPhone = z
  .string()
  .trim()
  .optional()
  .refine((value) => !value || INDIAN_MOBILE_REGEX.test(value), { message: PHONE_ERROR_MESSAGE });

// A sane ceiling against a pathological paste (megabytes of text), not a
// meaningful length in its own right — INDIAN_MOBILE_REGEX is what
// actually enforces "exactly 10 digits", by rejecting anything shorter
// or longer with PHONE_ERROR_MESSAGE. Deliberately NOT truncated to 10:
// silently dropping an 11th typed/pasted digit would turn a mistyped
// number into a different, validly-shaped one and submit it without the
// user ever noticing — an 11-digit entry must be flagged as wrong, not
// quietly rewritten into a wrong-but-valid-looking one.
const MAX_RAW_INPUT_LENGTH = 20;

/** Keystroke-level guard for every phone `<input>` — strips anything
 *  that isn't a digit, so letters/symbols/spaces (e.g. the "y" and
 *  spaces in "342412353435543445y45663") can never land in the field at
 *  all, not just get flagged after the fact. Runs in the input's
 *  onChange, ahead of react-hook-form's own, by mutating the
 *  (uncontrolled) DOM value in place before RHF reads it. */
export function sanitizePhoneInput(rawValue: string): string {
  return rawValue.replace(/\D/g, "").slice(0, MAX_RAW_INPUT_LENGTH);
}
