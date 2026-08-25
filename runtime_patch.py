from pathlib import Path

p = Path('xiaoxiao-Fetches-Warehouse-V2/scraper/scrape.py')
s = p.read_text(encoding='utf-8')

# Allow the workflow to provide a synthetic event file on push-triggered runs.
s = s.replace(
    "Path(os.environ['GITHUB_EVENT_PATH'])",
    "Path(os.environ.get('SCRAPER_EVENT_PATH', os.environ['GITHUB_EVENT_PATH']))"
)

# Structured checkout-discount logic. This parser only accepts explicit
# "Applied at Checkout" evidence and refuses ambiguous/mismatched discounts.
if 'from price_logic import extract_checkout_discount' not in s:
    s = s.replace(
        'from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError\n',
        'from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError\nfrom price_logic import extract_checkout_discount\n'
    )

start = s.index('async def click_variant(page,variant):')
end = s.index('\n\nasync def visible_price', start)

new_func = r'''async def click_variant(page,variant):
    if not variant: return False,''

    req_norm = norm(variant)
    req_tokens = tokens(variant)
    req_has_combo = 'combo' in req_norm

    # Exact accessible-name match first.
    pat=re.compile(r'^\s*'+re.escape(compact(variant))+r'\s*$',re.I)
    for role in ('button','radio','tab'):
        try:
            loc=page.get_by_role(role,name=pat)
            for i in range(min(await loc.count(),8)):
                el=loc.nth(i)
                if await el.is_visible():
                    await el.click(timeout=3000); await page.wait_for_timeout(1800); return True,f'clicked exact {role}'
        except Exception: pass

    # Collect visible interactive option labels and score them conservatively.
    candidates=[]

    for role in ('button','radio','tab'):
        try:
            loc=page.get_by_role(role)
            for i in range(min(await loc.count(),120)):
                el=loc.nth(i)
                if not await el.is_visible(): continue
                try: txt=compact(await el.inner_text())
                except Exception:
                    try: txt=compact(await el.get_attribute('aria-label') or '')
                    except Exception: txt=''
                if txt: candidates.append((el,txt,role))
        except Exception: pass

    try:
        loc=page.locator('label')
        for i in range(min(await loc.count(),160)):
            el=loc.nth(i)
            if not await el.is_visible(): continue
            try: txt=compact(await el.inner_text())
            except Exception: txt=''
            if txt: candidates.append((el,txt,'label'))
    except Exception: pass

    scored=[]
    for el,txt,kind in candidates:
        nt=norm(txt)
        if not nt: continue
        if not all(t in nt for t in req_tokens): continue

        # Critical safety rule: requesting a base/non-combo SKU must not select a Combo SKU.
        if not req_has_combo and 'combo' in nt: continue
        if req_has_combo and 'combo' not in nt: continue

        # Prefer the shortest matching option: e.g. "Creality Hi" over accessory bundles.
        extra=max(0,len(tokens(txt))-len(req_tokens))
        penalty=extra*10 + len(nt)
        scored.append((penalty,el,txt,kind))

    if scored:
        scored.sort(key=lambda x:x[0])
        _,el,txt,kind=scored[0]
        try:
            await el.click(timeout=3000)
            await page.wait_for_timeout(1800)
            return True,f'clicked fuzzy {kind}: {txt}'
        except Exception: pass

    return False,'requested variant/SKU not found as a unique non-conflicting option'
'''

s = s[:start] + new_func + s[end:]

# Add a conservative extractor for automatic checkout discount text. It only
# inspects visible evidence near the main product heading, then falls back to
# short body lines. Multiple distinct amounts are handled as AMBIGUOUS by
# price_logic.py, so no final price is calculated.
if 'async def checkout_discount_evidence(page):' not in s:
    marker = '\n\n@dataclass\nclass Result:'
    helper = r'''

async def checkout_discount_evidence(page):
    pattern = re.compile(
        r'(?:applied\s+at\s+checkout|apply\s+at\s+checkout|auto(?:matically)?[-\s]*applied\s+at\s+checkout|automatically\s+applied\s+at\s+checkout)',
        re.I
    )
    out=[]
    h1_y=None
    try:
        h1=page.locator('h1')
        for i in range(min(await h1.count(),5)):
            el=h1.nth(i)
            if await el.is_visible():
                box=await el.bounding_box()
                if box:
                    h1_y=box['y']
                    break
    except Exception:
        pass

    try:
        loc=page.get_by_text(pattern)
        for i in range(min(await loc.count(),60)):
            el=loc.nth(i)
            try:
                if not await el.is_visible(): continue
                txt=compact(await el.inner_text())
                if not txt or len(txt)>320 or not pattern.search(txt): continue
                box=await el.bounding_box()
                if h1_y is not None and box and not (h1_y-600 <= box['y'] <= h1_y+2400):
                    continue
                if txt not in out: out.append(txt)
            except Exception:
                continue
    except Exception:
        pass

    # Fallback for sites where the discount sentence is not exposed as a clean
    # text locator. Keep only short lines with the explicit checkout phrase.
    if not out:
        try:
            raw=await page.locator('body').inner_text()
            for line in raw.splitlines():
                txt=compact(line)
                if 4<=len(txt)<=320 and pattern.search(txt) and txt not in out:
                    out.append(txt)
                if len(out)>=12: break
        except Exception:
            pass
    return out
'''
    s = s.replace(marker, helper + marker)

# Extend result schema with structured automatic-discount fields.
old_fields = "final_url:str=''; http_status:int|None=None; detected_product:str=''; current_price:str=''; original_price:str=''; stock:str=''; promotion:str=''; status:str='UNVERIFIED'; method:str=''; reason:str=''; evidence:str=''; screenshot:str=''; captured_at_utc:str=''"
new_fields = "final_url:str=''; http_status:int|None=None; detected_product:str=''; current_price:str=''; original_price:str=''; automatic_discount:str=''; final_price:str=''; discount_status:str=''; discount_reason:str=''; discount_evidence:str=''; stock:str=''; promotion:str=''; status:str='UNVERIFIED'; method:str=''; reason:str=''; evidence:str=''; screenshot:str=''; captured_at_utc:str=''"
s = s.replace(old_fields, new_fields)

# Calculate final price only from an already VERIFIED current price plus one
# explicit and unambiguous automatic-checkout discount on the same page.
old_block = "        r.promotion=await promotions(page)\n        if r.status!='VERIFIED': r.reason=r.reason or 'Could not establish a reliable product/variant-to-price link. No price reported.'"
new_block = r'''        r.promotion=await promotions(page)
        if r.status=='VERIFIED' and r.current_price:
            checkout_texts=await checkout_discount_evidence(page)
            disc=extract_checkout_discount(checkout_texts, region, r.current_price)
            r.discount_status=disc.get('status','')
            r.automatic_discount=disc.get('automatic_discount','')
            r.final_price=disc.get('final_price','')
            r.discount_evidence=disc.get('evidence','')
            r.discount_reason=disc.get('reason','')
        else:
            r.discount_status='SKIPPED'
            r.discount_reason='Base product price was not VERIFIED, so checkout discount calculation was skipped.'
        if r.status!='VERIFIED': r.reason=r.reason or 'Could not establish a reliable product/variant-to-price link. No price reported.'
'''
if old_block not in s:
    raise RuntimeError('Could not locate promotion/finalization block for checkout-discount patch')
s = s.replace(old_block, new_block)

# Rebuild markdown output so automatic discount and calculated final price are
# explicit fields, never manually inferred later by the assistant.
md_start = s.index('def md(results):')
md_end = s.index('\n\nasync def main():', md_start)
new_md = r'''def md(results):
    out=['## Scrape result','',
         '| Region | Product | Variant | Current price | Original price | Auto checkout discount | Final price | Stock | Status |',
         '|---|---|---|---:|---:|---:|---:|---|---|']
    for r in results:
        out.append(
            f'| {r.region or "-"} | {r.requested_product or "-"} | {r.requested_variant or "-"} | '
            f'{r.current_price or "**—**"} | {r.original_price or "—"} | {r.automatic_discount or "—"} | '
            f'{r.final_price or "—"} | {r.stock or "—"} | **{r.status}** |'
        )
    out+=['','### Verification details','']
    for r in results:
        out += [
            f'**{r.region or "-"} — {r.requested_variant or r.requested_product}**',
            f'- Requested URL: {r.requested_url}',
            f'- Final URL: {r.final_url or "—"}',
            f'- Method: {r.method or "—"}',
            f'- Reason: {r.reason or "—"}',
            f'- Checkout discount status: {r.discount_status or "—"}',
            f'- Checkout discount reason: {r.discount_reason or "—"}'
        ]
        if r.evidence: out.append(f'- Price evidence: `{r.evidence[:800]}`')
        if r.discount_evidence: out.append(f'- Checkout discount evidence: `{r.discount_evidence[:800]}`')
        if r.promotion: out.append(f'- Promotion text: {r.promotion[:800]}')
        out.append('')
    out += [
        '---',
        '**Hard rules:** anything not `VERIFIED` gets no guessed/backfilled price; '
        'a final checkout price is shown only when `discount_status=VERIFIED` from explicit same-page checkout evidence.'
    ]
    return '\n'.join(out)
'''
s = s[:md_start] + new_md + s[md_end:]

p.write_text(s, encoding='utf-8')
print('runtime safety + checkout-discount patch applied')
