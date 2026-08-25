import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CURRENCY_RE = re.compile(r'(?P<currency>US\$|CA\$|AU\$|A\$|C\$|\$|€|£)\s*(?P<amount>\d[\d,.]*)', re.I)
PERCENT_RE = re.compile(r'(?P<amount>\d+(?:[.,]\d+)?)\s*%')
CHECKOUT_PHRASE_RE = re.compile(
    r'(?:applied\s+at\s+checkout|apply\s+at\s+checkout|auto(?:matically)?[-\s]*applied\s+at\s+checkout|automatically\s+applied\s+at\s+checkout)',
    re.I,
)

REGION_CURRENCY = {
    'US': ('USD', '$'),
    'EU': ('EUR', '€'),
    'UK': ('GBP', '£'),
    'AU': ('AUD', 'A$'),
    'CA': ('CAD', 'C$'),
}


def _compact(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _decimal_number(raw):
    s = (raw or '').strip().replace(' ', '')
    if not s:
        return None
    # Handle 1,299.00 and 1.299,00 conservatively by treating the last separator as decimal.
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        tail = s.rsplit(',', 1)[-1]
        s = s.replace(',', '.') if len(tail) in (1, 2) else s.replace(',', '')
    elif '.' in s:
        parts = s.split('.')
        if len(parts) > 2:
            tail = parts[-1]
            s = ''.join(parts[:-1]) + ('.' + tail if len(tail) in (1, 2) else tail)
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def canonical_currency(symbol, region=''):
    sym = (symbol or '').upper().replace(' ', '')
    region = (region or '').upper()
    if sym == '€':
        return 'EUR'
    if sym == '£':
        return 'GBP'
    if sym in {'A$', 'AU$'}:
        return 'AUD'
    if sym in {'C$', 'CA$'}:
        return 'CAD'
    if sym == 'US$':
        return 'USD'
    if sym == '$':
        return REGION_CURRENCY.get(region, ('USD', '$'))[0]
    return ''


def parse_money(text, region=''):
    m = CURRENCY_RE.search(text or '')
    if not m:
        return None
    amount = _decimal_number(m.group('amount'))
    if amount is None:
        return None
    return {
        'amount': amount,
        'currency': canonical_currency(m.group('currency'), region),
        'symbol': m.group('currency'),
        'raw': _compact(m.group(0)),
    }


def format_money(amount, region='', currency=''):
    region = (region or '').upper()
    currency = currency or REGION_CURRENCY.get(region, ('', ''))[0]
    symbol = REGION_CURRENCY.get(region, (currency, ''))[1]
    if not symbol:
        symbol = {'USD': '$', 'EUR': '€', 'GBP': '£', 'AUD': 'A$', 'CAD': 'C$'}.get(currency, '')
    amount = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if amount == amount.to_integral():
        return f'{symbol}{int(amount):,}'
    return f'{symbol}{amount:,.2f}'


def extract_checkout_discount(evidence_texts, region='', current_price=''):
    """
    Parse only explicit automatic-checkout discount evidence.

    Safety rules:
    - Generic "Save £150" is ignored.
    - The phrase must explicitly say the discount is applied at checkout.
    - Multiple distinct discount values => AMBIGUOUS; no final price.
    - Fixed discount currency must match the current product price currency.
    - Discount must be > 0 and < current price.
    """
    if isinstance(evidence_texts, str):
        evidence_texts = [evidence_texts]
    evidence_texts = [_compact(x) for x in (evidence_texts or []) if _compact(x)]

    current = parse_money(current_price, region)
    candidates = []

    for text in evidence_texts:
        if not CHECKOUT_PHRASE_RE.search(text):
            continue

        # Prefer a fixed currency amount, because that is what Flashforge currently shows.
        money = parse_money(text, region)
        if money:
            candidates.append({
                'type': 'fixed',
                'amount': money['amount'],
                'currency': money['currency'],
                'display': format_money(money['amount'], region, money['currency']),
                'evidence': text,
            })
            continue

        pct = PERCENT_RE.search(text)
        if pct:
            amount = _decimal_number(pct.group('amount'))
            if amount is not None:
                candidates.append({
                    'type': 'percent',
                    'amount': amount,
                    'currency': current['currency'] if current else '',
                    'display': f'{amount.normalize()}%',
                    'evidence': text,
                })

    if not candidates:
        return {
            'status': 'NOT_FOUND',
            'automatic_discount': '',
            'final_price': '',
            'evidence': '',
            'reason': 'No explicit automatic checkout discount was verified on the official product page.',
        }

    # Deduplicate identical values repeated by desktop/mobile/sticky DOM copies.
    unique = {}
    for c in candidates:
        key = (c['type'], str(c['amount']), c['currency'])
        unique.setdefault(key, c)
    candidates = list(unique.values())

    if len(candidates) != 1:
        return {
            'status': 'AMBIGUOUS',
            'automatic_discount': '',
            'final_price': '',
            'evidence': ' | '.join(c['evidence'] for c in candidates[:5]),
            'reason': 'Multiple distinct automatic checkout discounts were found; final price was not calculated.',
        }

    c = candidates[0]
    if not current:
        return {
            'status': 'UNVERIFIED',
            'automatic_discount': '',
            'final_price': '',
            'evidence': c['evidence'],
            'reason': 'Checkout discount was found, but the verified current price could not be parsed.',
        }

    if c['type'] == 'fixed':
        if c['currency'] and current['currency'] and c['currency'] != current['currency']:
            return {
                'status': 'CURRENCY_MISMATCH',
                'automatic_discount': '',
                'final_price': '',
                'evidence': c['evidence'],
                'reason': 'Checkout discount currency does not match the verified product price currency.',
            }
        discount_value = c['amount']
    else:
        if c['amount'] <= 0 or c['amount'] >= 100:
            return {
                'status': 'INVALID',
                'automatic_discount': '',
                'final_price': '',
                'evidence': c['evidence'],
                'reason': 'Checkout percentage discount is outside a valid range.',
            }
        discount_value = current['amount'] * c['amount'] / Decimal('100')

    if discount_value <= 0 or discount_value >= current['amount']:
        return {
            'status': 'INVALID',
            'automatic_discount': '',
            'final_price': '',
            'evidence': c['evidence'],
            'reason': 'Checkout discount is not a valid reduction from the verified current price.',
        }

    final_value = current['amount'] - discount_value
    return {
        'status': 'VERIFIED',
        'automatic_discount': c['display'],
        'final_price': format_money(final_value, region, current['currency']),
        'evidence': c['evidence'],
        'reason': 'Final price was calculated only from the verified current price and an explicit automatic checkout discount on the same official page.',
    }
