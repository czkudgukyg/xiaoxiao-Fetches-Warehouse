from pathlib import Path

p = Path('xiaoxiao-Fetches-Warehouse-V2/scraper/scrape.py')
s = p.read_text(encoding='utf-8')

# Allow the workflow to provide a synthetic event file on push-triggered runs.
s = s.replace(
    "Path(os.environ['GITHUB_EVENT_PATH'])",
    "Path(os.environ.get('SCRAPER_EVENT_PATH', os.environ['GITHUB_EVENT_PATH']))"
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
p.write_text(s, encoding='utf-8')
print('runtime patch applied')
