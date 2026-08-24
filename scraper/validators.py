import re
from urllib.parse import urlparse

REGION_CURRENCY = {"US": "USD", "EU": "EUR", "UK": "GBP", "AU": "AUD", "CA": "CAD"}


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def same_name(requested: str, detected: str) -> bool:
    """Require all meaningful requested tokens; never infer a different model."""
    a, b = normalize(requested).split(), set(normalize(detected).split())
    return bool(a) and all(token in b for token in a)


def expected_region(url: str, brand: str) -> str | None:
    parsed = urlparse(url)
    host, parts = parsed.hostname or "", [p.lower() for p in parsed.path.split("/") if p]
    if "bambulab" in host:
        sub = host.split(".")[0]
        return {"eu": "EU", "uk": "UK", "au": "AU", "ca": "CA"}.get(sub, "US")
    if "creality" in host:
        return parts[0].upper() if parts and parts[0] in {"eu", "uk", "au", "ca"} else "US"
    return None


def validate_region(url: str, requested: str) -> str | None:
    actual = expected_region(url, "")
    return None if actual == requested.upper() else f"URL region is {actual or 'unknown'}, requested {requested.upper()}"


def validate_currency(region: str, currency: str) -> str | None:
    expected = REGION_CURRENCY.get(region.upper())
    return None if expected == currency.upper() else f"Currency {currency or 'missing'} does not match {expected}"

