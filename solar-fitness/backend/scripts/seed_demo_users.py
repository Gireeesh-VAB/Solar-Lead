"""Seeds one dummy login per portal (customer, vendor, admin) for local dev.

Run:  uv run python scripts/seed_demo_users.py

Safe to re-run: existing users are left as-is, just their password is reset
to the demo value. The same credentials are what the login pages'
"Autofill test credentials" button fills in, via NEXT_PUBLIC_DEV_* in
frontend/.env.local. LOCAL DEV ONLY — never run against a real database.
"""

from solarfit.auth_users import hash_password
from solarfit.db import session_scope
from solarfit.repositories import users as users_repo
from solarfit.repositories import vendors as vendors_repo

DEMO_PASSWORD = "Demo@12345"

CUSTOMER = {"email": "customer@demo.com", "name": "Demo Customer"}
VENDOR = {"email": "vendor@demo.com", "name": "Demo Vendor"}
ADMIN = {"email": "admin@demo.com", "name": "Demo Admin"}


def _upsert(session, *, email, name, role, **extra):
    row = users_repo.get_by_email(session, email)
    if row is None:
        return users_repo.create_user(
            session,
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            name=name,
            role=role,
            **extra,
        )
    users_repo.update_password(session, row.id, password_hash=hash_password(DEMO_PASSWORD))
    return row


def main() -> None:
    with session_scope() as session:
        _upsert(
            session,
            **CUSTOMER,
            role="customer",
            owner_org="Demo Customer",
            status="active",
        )
        _upsert(session, **ADMIN, role="admin", status="active")

        vendor_user = users_repo.get_by_email(session, VENDOR["email"])
        vendor_id = vendor_user.vendor_id if vendor_user else None
        if vendor_id is None:
            vendor = vendors_repo.create_vendor(
                session,
                name="Demo Solar Surveyors",
                payout_method_type="UPI",
                payout_masked_account="demo@upi",
                service_area={"region": "Telangana", "districts": ["Hyderabad", "Rangareddy"]},
                verification_status="verified",
                contact_name="Demo Vendor",
                contact_email=VENDOR["email"],
            )
            vendor_id = vendor.id
        _upsert(session, **VENDOR, role="vendor", vendor_id=vendor_id, status="active")

    print("Seeded demo users (password for all):", DEMO_PASSWORD)
    for label, u in (("customer", CUSTOMER), ("vendor", VENDOR), ("admin", ADMIN)):
        print(f"  {label:9s} {u['email']}")


if __name__ == "__main__":
    main()
