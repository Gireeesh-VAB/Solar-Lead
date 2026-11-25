// -----------------------------------------------------------------------------
// Real auth calls against /app/auth/* — the one place LoginForm/SignupForm/
// UserMenu go through, rather than each building its own fetchClient calls.
// -----------------------------------------------------------------------------

import { apiFetch } from "@/lib/api/fetchClient";
import {
  clearStoredSession,
  setStoredSession,
  type PortalRole,
  type StoredSession,
} from "@/lib/auth/session";

interface UserOut {
  id: string;
  email: string;
  role: string;
  name: string;
  ownerOrg: string | null;
  vendorId: string | null;
  tier: string | null;
  status: string | null;
  billingContactEmail: string | null;
  createdAt: string;
}

interface AuthResponse {
  token: string;
  user: UserOut;
}

function toStoredSession(response: AuthResponse): StoredSession {
  return {
    token: response.token,
    userId: response.user.id,
    role: response.user.role as PortalRole,
    name: response.user.name,
    email: response.user.email,
  };
}

export async function login(email: string, password: string): Promise<StoredSession> {
  const response = await apiFetch<AuthResponse>("/app/auth/login", {
    method: "POST",
    body: { email, password },
  });
  const session = toStoredSession(response);
  setStoredSession(session);
  return session;
}

export interface SignupInput {
  name: string;
  email: string;
  password: string;
  phone?: string;
}

export async function signup(input: SignupInput): Promise<StoredSession> {
  const response = await apiFetch<AuthResponse>("/app/auth/signup", {
    method: "POST",
    body: {
      name: input.name,
      email: input.email,
      password: input.password,
      // Self-service signup has no company name to offer — ownerOrg is a
      // required free-text field on the backend (it groups paid tenant
      // seats), so an individual consumer gets their own email as a
      // synthetic one-person org. The consumer "checks" flow scopes by
      // the user's id, not this value, so it's otherwise unused for them.
      ownerOrg: input.email,
    },
  });
  const session = toStoredSession(response);
  setStoredSession(session);

  if (input.phone) {
    try {
      await apiFetch("/app/customer/profile", {
        method: "PATCH",
        body: { phone: input.phone },
      });
    } catch {
      // Non-fatal — the account and session are already created; the
      // customer can set their phone later from the profile page.
    }
  }

  return session;
}

export function logout(): void {
  clearStoredSession();
}

export async function getMe(): Promise<UserOut> {
  return apiFetch<UserOut>("/app/auth/me");
}
