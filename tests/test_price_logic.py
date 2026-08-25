import sys
import unittest
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parents[1] / 'xiaoxiao-Fetches-Warehouse-V2' / 'scraper'
sys.path.insert(0, str(SCRAPER_DIR))

from price_logic import extract_checkout_discount


class CheckoutDiscountTests(unittest.TestCase):
    def check(self, region, current, evidence, expected_discount, expected_final):
        out = extract_checkout_discount([evidence], region, current)
        self.assertEqual(out['status'], 'VERIFIED', out)
        self.assertEqual(out['automatic_discount'], expected_discount)
        self.assertEqual(out['final_price'], expected_final)

    def test_flashforge_us(self):
        self.check('US', '$449', '$80 Off Applied at Checkout', '$80', '$369')

    def test_flashforge_eu(self):
        self.check('EU', '€499', '€120 Off Applied at Checkout', '€120', '€379')

    def test_flashforge_uk_regression(self):
        # Regression test for the exact error that previously produced £319.
        self.check('UK', '£399', '£60 Off Applied at Checkout', '£60', '£339')

    def test_flashforge_uk_fullwidth_pound_regression(self):
        # Flashforge UK currently renders a compatibility/fullwidth pound sign: ￡60.
        # It must normalize to £60 before arithmetic.
        self.check('UK', '£399', '￡60 Off Applied at Checkout', '£60', '£339')

    def test_flashforge_au(self):
        self.check('AU', 'A$749', 'A$180 Off Applied at Checkout', 'A$180', 'A$569')

    def test_flashforge_ca(self):
        self.check('CA', 'C$599', 'C$130 Off Applied at Checkout', 'C$130', 'C$469')

    def test_generic_save_is_not_checkout_discount(self):
        out = extract_checkout_discount(['Save £150'], 'UK', '£399')
        self.assertEqual(out['status'], 'NOT_FOUND')
        self.assertEqual(out['automatic_discount'], '')
        self.assertEqual(out['final_price'], '')

    def test_plain_off_without_checkout_is_not_accepted(self):
        out = extract_checkout_discount(['£80 OFF today only'], 'UK', '£399')
        self.assertEqual(out['status'], 'NOT_FOUND')

    def test_multiple_distinct_checkout_discounts_are_ambiguous(self):
        out = extract_checkout_discount(
            ['£60 Off Applied at Checkout', '£80 Off Applied at Checkout'],
            'UK',
            '£399',
        )
        self.assertEqual(out['status'], 'AMBIGUOUS')
        self.assertEqual(out['automatic_discount'], '')
        self.assertEqual(out['final_price'], '')

    def test_currency_mismatch_is_rejected(self):
        out = extract_checkout_discount(['€60 Off Applied at Checkout'], 'UK', '£399')
        self.assertEqual(out['status'], 'CURRENCY_MISMATCH')
        self.assertEqual(out['final_price'], '')

    def test_duplicate_dom_copies_are_safe(self):
        out = extract_checkout_discount(
            ['£60 Off Applied at Checkout', '£60 Off Applied at Checkout'],
            'UK',
            '£399',
        )
        self.assertEqual(out['status'], 'VERIFIED')
        self.assertEqual(out['final_price'], '£339')


if __name__ == '__main__':
    unittest.main()
