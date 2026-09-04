"""Amazon product image URLs derived from an ASIN.
The warehouse stores no image hashes, so the public per-ASIN endpoint is used."""

from __future__ import annotations

import re

ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")

SIZES = {
    "thumb": "SL160",
    "card": "SL500",
    "large": "SL1000",
}


def product_image(asin: str | None, size: str = "card") -> str:
    """Public Amazon image URL for an ASIN, or an empty string when unusable."""
    if not asin:
        return ""
    code = asin.strip().upper()
    if not ASIN_PATTERN.match(code):
        return ""
    suffix = SIZES.get(size, SIZES["card"])
    return f"https://images-na.ssl-images-amazon.com/images/P/{code}.01._{suffix}_.jpg"


def product_link(asin: str | None, marketplace_domain: str = "amazon.com") -> str:
    """Canonical Amazon detail-page link for an ASIN."""
    if not asin:
        return ""
    code = asin.strip().upper()
    if not ASIN_PATTERN.match(code):
        return ""
    return f"https://www.{marketplace_domain}/dp/{code}"
