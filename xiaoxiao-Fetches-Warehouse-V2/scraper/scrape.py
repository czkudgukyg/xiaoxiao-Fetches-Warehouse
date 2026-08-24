#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio, json, os, re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

PRICE_RE = re.compile(r'(?<!\w)(?:US\$|CA\$|AU\$|A\$|C\$|\$|€|£)\s?\d[\d,.]*')
PROMO_RE = re.compile(r'\b(?:save|off|sale|deal|discount|coupon|credit|credits|limited[- ]time|anniversary|back[- ]to[- ]school|bundle|free gift|promo(?:tion)?)\b', re.I)
PREFIX = {'US':'$','EU':'€','UK':'£','AU':'A$','CA':'C$'}


def compact(s): return re.sub(r'\s+', ' ', s or '').strip()
def norm(s): return compact(re.sub(r'[^\w]+',' ',compact(s).lower()))
def tokens(s): return [x for x in norm(s).split() if x not in {'3d','printer','printers','lab','the','a','an','with'} and len(x)>1]
def name_match(expected, actual):
    t=tokens(expected); a=norm(actual); return bool(t) and all(x in a for x in t)


def payload_from_issue():
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    body=(event.get('issue') or {}).get('body') or ''
    m=re.search(r'```(?:json)?\s*(\{.*?\})\s*```',body,re.S|re.I)
    raw=m.group(1) if m else body[body.find('{'):body.rfind('}')+1]
    data=json.loads(raw)
    if not isinstance(data.get('targets'),list) or not data['targets']:
        raise ValueError('targets must be a non-empty list')
    return data


async def fetch_product_js(page):
    p=urlparse(page.url); path=p.path.rstrip('/')
    if '/products/' not in path: return None,''
    u=f'{p.scheme}://{p.netloc}{path}.js'
    try:
        obj=await page.evaluate("""async u=>{try{let r=await fetch(u,{credentials:'include'});return {s:r.status,t:await r.text()}}catch(e){return {s:0,t:String(e)}}}""",u)
        if obj.get('s')==200:
            data=json.loads(obj.get('t') or '')
            if isinstance(data,dict) and data.get('title'): return data,u
    except Exception: pass
    return None,u


def cents(v,region):
    if v is None: return ''
    try: n=int(v)/100
    except Exception: return ''
    return f"{PREFIX.get(region,'')}{int(n):,}" if n.is_integer() else f"{PREFIX.get(region,'')}{n:,.2f}"


def match_shopify_variant(data,target):
    vs=data.get('variants') or []; variant=compact(target.get('variant') or '')
    q=parse_qs(urlparse(target.get('url') or '').query)
    ids=sum([q.get(k,[]) for k in ('variant','id')],[])
    for v in vs:
        if str(v.get('id')) in ids: return v,'SHOPIFY_VARIANT_ID'
    if variant:
        exact=[v for v in vs if norm(v.get('title') or '')==norm(variant)]
        if len(exact)==1: return exact[0],'SHOPIFY_VARIANT_TITLE_EXACT'
        tm=[v for v in vs if name_match(variant,v.get('title') or '')]
        if len(tm)==1: return tm[0],'SHOPIFY_VARIANT_TITLE_TOKENS'
        if len(vs)==1 and name_match(variant,data.get('title') or ''): return vs[0],'SHOPIFY_SINGLE_VARIANT_PRODUCT_TITLE'
        return None,'VARIANT_NOT_UNIQUELY_MATCHED'
    if not name_match(target.get('product') or '',data.get('title') or ''): return None,'PRODUCT_TITLE_MISMATCH'
    if len(vs)==1: return vs[0],'SHOPIFY_SINGLE_VARIANT'
    if len({v.get('price') for v in vs})==1 and len({v.get('compare_at_price') for v in vs})<=1:
        out=dict(vs[0]); av={v.get('available') for v in vs}; out['available']=av.pop() if len(av)==1 else None
        return out,'SHOPIFY_ALL_VARIANTS_SAME_PRICE'
    return None,'MULTIPLE_VARIANTS_AMBIGUOUS'


async def click_variant(page,variant):
    if not variant: return False,''
    pat=re.compile(r'^\s*'+re.escape(compact(variant))+r'\s*$',re.I)
    for role in ('button','radio','tab'):
        try:
            loc=page.get_by_role(role,name=pat)
            for i in range(min(await loc.count(),5)):
                el=loc.nth(i)
                if await el.is_visible():
                    await el.click(timeout=3000); await page.wait_for_timeout(1800); return True,f'clicked {role}'
        except Exception: pass
    try:
        loc=page.locator('label')
        for i in range(min(await loc.count(),100)):
            el=loc.nth(i)
            if await el.is_visible() and norm(await el.inner_text())==norm(variant):
                await el.click(timeout=3000); await page.wait_for_timeout(1800); return True,'clicked label'
    except Exception: pass
    return False,'exact interactive variant label not found'


async def visible_price(page,target,variant_clicked):
    body=compact(await page.locator('body').inner_text()); expected=target.get('variant') or target.get('product') or ''
    if not name_match(expected,body): return None
    if target.get('variant') and not variant_clicked: return None
    h1box=None; h1=page.locator('h1')
    for i in range(min(await h1.count(),5)):
        try:
            if await h1.nth(i).is_visible(): h1box=await h1.nth(i).bounding_box(); break
        except Exception: pass
    c=[]
    for sel in ['[data-testid*="price" i]','[class*="sale-price" i]','[class*="current-price" i]','[class*="product-price" i]','[class*="price" i]']:
        try:
            loc=page.locator(sel)
            for i in range(min(await loc.count(),120)):
                el=loc.nth(i)
                if not await el.is_visible(): continue
                txt=compact(await el.inner_text()); ps=PRICE_RE.findall(txt)
                if not ps: continue
                cls=compact(await el.get_attribute('class') or '').lower(); tag=(await el.evaluate('(e)=>e.tagName')).lower(); box=await el.bounding_box()
                if not box: continue
                old=tag in {'del','s'} or any(x in cls for x in ['compare','original','regular','old','was','line-through'])
                for p in ps: c.append({'p':compact(p),'y':box['y'],'old':old,'txt':txt[:250]})
        except Exception: pass
    cur=[x for x in c if not x['old']]
    if h1box:
        local=[x for x in cur if h1box['y']-120<=x['y']<=h1box['y']+800]
        if local: cur=sorted(local,key=lambda x:abs(x['y']-(h1box['y']+h1box['height'])))
    if not cur: return None
    old=[x for x in c if x['old']]; original=''
    if old:
        near=sorted(old,key=lambda x:abs(x['y']-cur[0]['y']))[0]
        if abs(near['y']-cur[0]['y'])<250: original=near['p']
    return {'current':cur[0]['p'],'original':original,'evidence':cur[0]['txt']}


async def promotions(page):
    try: text=await page.locator('body').inner_text()
    except Exception: return ''
    out=[]
    for raw in text.splitlines():
        line=compact(raw)
        if 5<=len(line)<=220 and PROMO_RE.search(line) and line not in out: out.append(line)
        if len(out)>=4: break
    return ' | '.join(out)


@dataclass
class Result:
    region:str; requested_product:str; requested_variant:str; requested_url:str
    final_url:str=''; http_status:int|None=None; detected_product:str=''; current_price:str=''; original_price:str=''; stock:str=''; promotion:str=''; status:str='UNVERIFIED'; method:str=''; reason:str=''; evidence:str=''; screenshot:str=''; captured_at_utc:str=''


async def scrape(browser,target,idx):
    region=compact(target.get('region') or '').upper(); product=compact(target.get('product') or ''); variant=compact(target.get('variant') or ''); url=compact(target.get('url') or '')
    r=Result(region,product,variant,url,captured_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    ctx=await browser.new_context(viewport={'width':1440,'height':1250},locale='en-US',user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36')
    page=await ctx.new_page()
    try:
        resp=await page.goto(url,wait_until='domcontentloaded',timeout=60000); r.http_status=resp.status if resp else None; r.final_url=page.url
        if resp and resp.status>=400:
            r.status='ACCESS_FAILED'; r.reason=f'Official page returned HTTP {resp.status}. No price reported.'; return r
        try: await page.wait_for_load_state('networkidle',timeout=20000)
        except PlaywrightTimeoutError: pass
        await page.wait_for_timeout(2500); r.final_url=page.url
        shots=Path('reports/screenshots'); shots.mkdir(parents=True,exist_ok=True); shot=shots/f'{idx:02d}_{region or "NA"}.png'
        try: await page.screenshot(path=str(shot),full_page=True); r.screenshot=str(shot)
        except Exception: pass
        title=compact(await page.title()); body=compact(await page.locator('body').inner_text()); h1=page.locator('h1'); hs=[]
        for i in range(min(await h1.count(),5)):
            try:
                if await h1.nth(i).is_visible(): hs.append(compact(await h1.nth(i).inner_text()))
            except Exception: pass
        r.detected_product=hs[0] if hs else title
        if urlparse(url).path.rstrip('/')!=urlparse(page.url).path.rstrip('/') and not name_match(variant or product,r.detected_product+' '+body[:4000]):
            r.status='REDIRECTED_OTHER_PRODUCT'; r.reason='Supplied URL redirected to a different product/page. No requested-product price reported.'; r.evidence=f'title={title}; detected={r.detected_product}'; return r
        clicked,note=await click_variant(page,variant)
        if clicked: body=compact(await page.locator('body').inner_text())
        data,pjs=await fetch_product_js(page)
        if data:
            if not (name_match(product,data.get('title') or '') or name_match(variant or product,data.get('title') or '')):
                r.status='PRODUCT_MISMATCH'; r.reason='Official product data does not match requested product. No price reported.'; r.evidence=f'product.js title={data.get("title")}'; return r
            mv,method=match_shopify_variant(data,target)
            if mv:
                r.current_price=cents(mv.get('price'),region); r.original_price=cents(mv.get('compare_at_price'),region); av=mv.get('available'); r.stock='In Stock' if av is True else ('Sold Out' if av is False else 'Unknown')
                if r.current_price:
                    r.status='VERIFIED'; r.method=method; r.reason='Price is tied to requested product/variant in official same-origin product data.'; r.evidence=f'product.js={pjs}; title={data.get("title")}; variant={mv.get("title")}; id={mv.get("id")}; {note}'
            elif method in {'VARIANT_NOT_UNIQUELY_MATCHED','MULTIPLE_VARIANTS_AMBIGUOUS'}:
                r.status='UNVERIFIED'; r.reason='Official product data accessible, but requested variant not uniquely matched. No price reported.'; r.evidence=f'{pjs}; {method}; {note}'; return r
        if r.status!='VERIFIED':
            vp=await visible_price(page,target,clicked)
            if vp:
                r.current_price=vp['current']; r.original_price=vp['original']; low=body.lower(); r.stock='Sold Out' if any(x in low for x in ['sold out','out of stock','currently unavailable']) else ('In Stock' if any(x in low for x in ['add to cart','buy now','in stock']) else 'Unknown'); r.status='VERIFIED'; r.method='VISIBLE_DOM_NEAR_PRODUCT_TITLE'; r.reason='Visible official-page price tied to requested product after identity/variant checks.'; r.evidence=vp['evidence']
        r.promotion=await promotions(page)
        if r.status!='VERIFIED': r.reason=r.reason or 'Could not establish a reliable product/variant-to-price link. No price reported.'
    except Exception as e:
        r.status='ACCESS_FAILED'; r.reason=f'{type(e).__name__}: {e}. No price reported.'
    finally: await ctx.close()
    return r


def md(results):
    out=['## Scrape result','','| Region | Product | Variant | Current price | Original price | Stock | Status |','|---|---|---|---:|---:|---|---|']
    for r in results: out.append(f'| {r.region or "-"} | {r.requested_product or "-"} | {r.requested_variant or "-"} | {r.current_price or "**—**"} | {r.original_price or "—"} | {r.stock or "—"} | **{r.status}** |')
    out+=['','### Verification details','']
    for r in results:
        out += [f'**{r.region or "-"} — {r.requested_variant or r.requested_product}**',f'- Requested URL: {r.requested_url}',f'- Final URL: {r.final_url or "—"}',f'- Method: {r.method or "—"}',f'- Reason: {r.reason or "—"}']
        if r.evidence: out.append(f'- Evidence: `{r.evidence[:800]}`')
        if r.promotion: out.append(f'- Promotion text: {r.promotion[:800]}')
        out.append('')
    out += ['---','**Hard rule:** anything not `VERIFIED` gets no guessed/backfilled price.']
    return '\n'.join(out)


async def main():
    targets=payload_from_issue()['targets']
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage']); rs=[]
        for i,t in enumerate(targets,1): rs.append(await scrape(b,t,i))
        await b.close()
    Path('reports').mkdir(exist_ok=True); Path('reports/result.json').write_text(json.dumps({'captured_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'results':[asdict(x) for x in rs]},ensure_ascii=False,indent=2),encoding='utf-8'); Path('reports/result.md').write_text(md(rs),encoding='utf-8'); print(md(rs))

if __name__=='__main__': asyncio.run(main())
