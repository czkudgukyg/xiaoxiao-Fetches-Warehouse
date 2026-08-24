import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, Page, Response

from .network_parser import json_candidates

LOG = logging.getLogger(__name__)


async def capture(browser: Browser, url: str, screenshot: Path) -> tuple[Page, Response | None, list[dict]]:
    context = await browser.new_context(locale="en-US")
    page = await context.new_page()
    evidence: list[dict] = []

    async def record(response: Response) -> None:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type or urlparse(response.url).hostname != urlparse(url).hostname:
            return
        try:
            body = await response.text()
            parsed = json_candidates(body)
            if parsed:
                evidence.append({"type": "official_network_json", "url": response.url, "data": parsed[:100]})
        except Exception as exc:  # response bodies can expire/stream
            LOG.debug("Could not inspect %s: %s", response.url, exc)

    page.on("response", record)
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        LOG.info("Network remained active; continuing after bounded wait")
    await page.wait_for_timeout(2_000)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(screenshot), full_page=True)
    evidence.append({"type": "final_url", "value": page.url})
    for script in await page.locator('script[type="application/ld+json"]').all_text_contents():
        try:
            evidence.append({"type": "ld_json", "data": json.loads(script)})
        except ValueError:
            continue
    return page, response, evidence

