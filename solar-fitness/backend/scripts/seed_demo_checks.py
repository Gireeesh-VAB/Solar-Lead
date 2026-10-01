"""Seeds a handful of demo customer checks, for showing the flow.

Run:  uv run python scripts/seed_demo_checks.py [--user sam@demo.com]

Each seeded check goes through the REAL pipeline — real Google Solar API
geometry, the real usable-area calculation, the real constraint packs.
Nothing here writes a fabricated verdict or capacity; the only thing this
script supplies is what a customer would have typed: an address, a pin,
and their monthly bill range.

The locations are deliberately ones with confirmed Solar API coverage.
Coverage in India is patchy, and a demo that silently degrades to
"insufficient data" is worse than no demo.

Safe to re-run: every check is created fresh, so seeding twice gives two
sets. It never deletes anything.
"""

import argparse
import sys

import httpx
from sqlalchemy import text

from solarfit.auth_users import create_access_token
from solarfit.db import get_engine

API = "http://localhost:8000"

# (label, lat, lng, bill low, bill high) — the bill range is what makes
# each one land on a different binding constraint, which is the thing
# worth showing.
DEMO_CHECKS = [
    ("Kukatpally — modest household", 17.441683, 78.396561, 1200, 2400),
    ("Kukatpally — family home", 17.441716, 78.396555, 3000, 6000),
    ("Himayatnagar — large home", 17.386000, 78.487000, 5000, 9000),
    ("Himayatnagar — small business", 17.385000, 78.486700, 15000, 30000),
    ("Kukatpally — no bill given", 17.441678, 78.396539, None, None),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="sam@demo.com", help="customer to own the checks")
    parser.add_argument("--api", default=API)
    args = parser.parse_args()

    with get_engine().connect() as conn:
        row = conn.execute(
            text("select id, email, role from users where email = :e"), {"e": args.user}
        ).first()
    if row is None:
        print(f"No such user: {args.user}", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {create_access_token(str(row[0]), row[2])}"}
    print(f"Seeding {len(DEMO_CHECKS)} checks as {row[1]}\n")

    created = 0
    for label, lat, lng, low, high in DEMO_CHECKS:
        body: dict = {
            "address": label,
            "lat": lat,
            "lng": lng,
            "siteType": "ROOFTOP_RESIDENTIAL",
        }
        if low is not None and high is not None:
            body["monthlyBillLowInr"] = low
            body["monthlyBillHighInr"] = high

        try:
            response = httpx.post(f"{args.api}/app/checks", json=body, headers=headers, timeout=180)
            response.raise_for_status()
            check_id = response.json()["id"]

            # The real assessment — same endpoint the customer's own
            # processing page calls.
            assessed = httpx.post(
                f"{args.api}/app/checks/{check_id}/complete", headers=headers, timeout=300
            )
            assessed.raise_for_status()
        except httpx.HTTPError as exc:
            # An external provider hiccup on one location must not abandon
            # the rest of the seed.
            print(f"  {label:36} FAILED — {exc}")
            continue

        latest = assessed.json().get("latestAssessment") or {}
        binding = (latest.get("bindingConstraint") or {}).get("name")
        print(
            f"  {label:36} {latest.get('capacityKwp', 0):7.2f} kWp  "
            f"{latest.get('verdict', '?'):28} binding={binding}"
        )
        created += 1

    print(f"\n{created}/{len(DEMO_CHECKS)} seeded. Open http://localhost:3000/checks")
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
