import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .browser import capture
from .models import Result, Target
from .network_parser import product_candidates
from .validators import same_name, validate_currency, validate_region


def money(value):
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value")
    try:
        number = float(value)
        return number / 100 if number.is_integer() and number >= 10000 else number
    except (ValueError, TypeError):
        return None


def currency(value, candidate):
    if isinstance(value, dict):
        return str(value.get("currencyCode") or value.get("currency") or "").upper()
    return str(candidate.get("currency") or candidate.get("currencyCode") or "").upper()


async def scrape_storefront(browser, target: Target, screenshot: Path) -> Result:
    r = Result(brand=target.brand, region=target.region.upper(), requested_product=target.product,
               requested_variant=target.variant, input_url=target.url, domain=urlparse(target.url).hostname or "",
               screenshot_path=str(screenshot))
    mismatch = validate_region(target.url, target.region)
    if mismatch:
        r.verification_reason = mismatch
        return r
    try:
        page, response, evidence = await capture(browser, target.url, screenshot)
        r.final_url, r.http_status, r.raw_evidence = page.url, response.status if response else None, evidence
        if r.http_status in {401, 402, 403, 429}:
            r.verification_status, r.verification_reason = "HTTP_BLOCKED", f"HTTP {r.http_status}"
            return r
        title = (await page.locator("h1").first.text_content() or "").strip()
        r.detected_product = title
        r.raw_evidence.append({"type": "product_title", "value": title})
        if not same_name(target.product, title):
            r.verification_status = "PRODUCT_REDIRECT" if page.url != target.url else "PRODUCT_NOT_FOUND"
            r.verification_reason = f"Detected title '{title}' does not match requested product"
            return r
        candidates = product_candidates([e.get("data") for e in evidence if e.get("data")])
        requested = target.variant
        query = parse_qs(urlparse(target.url).query)
        requested_id = (query.get("id") or query.get("variant") or [""])[0]
        if requested_id:
            id_matches = [c for c in candidates if str(c.get("id") or c.get("variantId") or "") == requested_id]
            if not id_matches:
                r.variant_id = requested_id
                r.verification_status, r.verification_reason = "VARIANT_MISMATCH", "URL variant ID absent from official product data"
                return r
            candidates = id_matches
        matches = [c for c in candidates if same_name(requested, str(c.get("title") or c.get("name") or ""))]
        if not matches:
            r.verification_status, r.verification_reason = "VARIANT_MISMATCH", "No official data record matched requested variant"
            return r
        c = matches[0]
        r.detected_variant = str(c.get("title") or c.get("name") or "")
        r.variant_id = str(c.get("id") or c.get("variantId") or "")
        price_value = c.get("price") or c.get("priceAmount") or c.get("salePrice")
        r.current_price = money(price_value)
        r.compare_at_price = money(c.get("compare_at_price") or c.get("compareAtPrice"))
        r.currency = currency(price_value, c)
        r.available = c.get("available") if isinstance(c.get("available"), bool) else None
        r.stock_status = "OUT_OF_STOCK" if r.available is False else "IN_STOCK" if r.available else "UNKNOWN"
        r.raw_evidence.append({"type": "matched_variant", "data": c})
        r.data_source = "official_network_or_embedded_json"
        if r.current_price is None:
            r.verification_status, r.verification_reason = "PRICE_NOT_FOUND", "Matched variant has no reliable current price"
        elif (reason := validate_currency(r.region, r.currency)):
            r.verification_reason = reason
        else:
            r.verification_status, r.verification_reason = "VERIFIED", "Product, variant, region, currency and price matched"
        return r
    except Exception as exc:
        r.verification_status, r.verification_reason = "ERROR", f"{type(exc).__name__}: {exc}"
        return r
