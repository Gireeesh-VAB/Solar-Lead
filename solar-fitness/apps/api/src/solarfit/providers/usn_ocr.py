"""STUB — Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.15 USN Capture (USN-01..06) of
Solar_Fitness_Engine_Development_Document_v1.1. Scoped to
ROOFTOP_RESIDENTIAL / ROOFTOP_CI only (BILLING_LINKED_SITE_TYPES in
solarfit.domain.site).

  USN-01  Manual text entry — baseline path.
  USN-02  OCR from an uploaded electricity bill; confirm-before-store.
  USN-03  OCR from a payment-proof/transaction screenshot; same
          confirm-before-store discipline.
  USN-04  Converge all three paths into one usn + usn_source
          (see solarfit.domain.site.UsnCapture — already defined).
  USN-05  Coordinate with Person 1: SITE-02's JSON Schema must omit this
          field group entirely for non-billing-linked site types.
  USN-06  Bill/payment-proof images used purely for OCR: encrypted at
          rest, retention window, hard-excluded from ML/vision training.

Depends on: solarfit.domain.site.UsnCapture (frozen, Day 0).

Add a managed OCR/Document-AI SDK to apps/api/pyproject.toml when you
start this — deliberately not pre-installed by the Day-0 foundation.
"""

from solarfit.domain.site import UsnCapture


def capture_manual(usn: str) -> UsnCapture:
    """USN-01."""
    return UsnCapture(usn=usn, usn_source="manual")


def extract_from_bill(image: bytes) -> UsnCapture:
    """USN-02. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError


def extract_from_payment_proof(image: bytes) -> UsnCapture:
    """USN-03. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError
