# Competitor Store Price Scraper V2

An evidence-first Python 3.11/Playwright scraper for **only the supplied official URL and that page's own same-host data requests**. It never searches, substitutes another region/product/variant, or guesses a price. Bambu Lab and Creality are routed through brand adapters; more adapters can reuse the strict common pipeline.

## Verification contract

The scraper captures the final URL, HTTP status, page title, official JSON/JSON-LD, matched variant record, and a full-page screenshot. A price is `VERIFIED` only when product and requested variant names match, the current price is bound to that variant record, and URL region/currency agree. A compare-at price is read only from that same record. Missing or ambiguous evidence produces an explicit failure (`UNVERIFIED`, `VARIANT_MISMATCH`, `PRODUCT_REDIRECT`, `HTTP_BLOCKED`, `PRICE_NOT_FOUND`, `PRODUCT_NOT_FOUND`, or `ERROR`) with no price substitution.

HTTP 401/402/403/429 is recorded as `HTTP_BLOCKED`; no bypass is attempted. A future deployment may supply a compliant remote Playwright connection (Browserless) or approved regional proxy, but it must retain the same URL/evidence rules.

## Local use

```bash
python -m pip install -r requirements.txt
playwright install chromium
python -m scraper.main --batch examples/targets.json
```

Or one target:

```bash
python -m scraper.main \
  --brand Creality --region US --product "K2 Plus Combo" \
  --variant "K2 Plus Combo" \
  --url "https://store.creality.com/products/creality-k2-plus-combo-3d-printer"
```

Outputs are `reports/latest.json`, `reports/latest.csv`, and `screenshots/<stable-task-id>/<REGION>.png`. JSON results contain the documented standard fields and raw evidence supporting the decision. Logs explicitly report each requested URL and outcome.

## GitHub Actions

Run **Competitor price scrape** from Actions. Supply either all five single-target inputs or `batch_json` (a JSON array shaped like `examples/targets.json`). The workflow installs Chromium, runs the scraper, and always uploads `competitor-scrape-result` containing reports and screenshots.

The example batch contains all ten initial Creality K2 Plus Combo and Creality Hi regional checks. Live storefront results are intentionally not committed as timeless facts: dispatch the workflow to capture current evidence and download the artifact. A redirect such as Creality Hi to SPARKX i7 is reported as `PRODUCT_REDIRECT`, never as a valid Hi price.

## Tests

```bash
python -m unittest discover -s tests -v
```

