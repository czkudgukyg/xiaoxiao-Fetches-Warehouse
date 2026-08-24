import argparse
import asyncio
import csv
import hashlib
import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from .models import Target


def targets(args) -> list[Target]:
    if args.batch:
        raw = json.loads(Path(args.batch).read_text()) if Path(args.batch).exists() else json.loads(args.batch)
    else:
        raw = [{"brand": args.brand, "region": args.region, "product": args.product,
                "variant": args.variant, "url": args.url}]
    if not isinstance(raw, list) or not raw:
        raise ValueError("Batch input must be a non-empty JSON array")
    required = {"brand", "region", "product", "variant", "url"}
    for item in raw:
        missing = required - item.keys()
        if missing:
            raise ValueError(f"Target is missing: {', '.join(sorted(missing))}")
    return [Target(**item) for item in raw]


async def run(items: list[Target], report_dir: Path, screenshot_dir: Path) -> list[dict]:
    output = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for item in items:
            task_id = item.task_id or hashlib.sha256(item.url.encode()).hexdigest()[:12]
            shot = screenshot_dir / task_id / f"{item.region.upper()}.png"
            logging.info("Scraping only requested URL: %s", item.url)
            module = __import__("scraper.bambu" if "bambu" in item.brand.lower() else "scraper.creality", fromlist=["scrape"])
            result = await module.scrape(browser, item, shot)
            logging.info("Result: %s - %s", result.verification_status, result.verification_reason)
            output.append(result.dict())
            try:
                await browser.contexts[-1].close()
            except IndexError:
                pass
        await browser.close()
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "latest.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    with (report_dir / "latest.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in output)
    return output


def cli():
    parser = argparse.ArgumentParser(description="Strict official-store variant price scraper")
    parser.add_argument("--batch", help="JSON string or JSON file")
    for name in ("brand", "region", "product", "variant", "url"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--screenshot-dir", default="screenshots")
    args = parser.parse_args()
    if not args.batch and not all(getattr(args, key) for key in ("brand", "region", "product", "variant", "url")):
        parser.error("provide --batch or every single-target argument")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(targets(args), Path(args.report_dir), Path(args.screenshot_dir)))


if __name__ == "__main__":
    cli()

