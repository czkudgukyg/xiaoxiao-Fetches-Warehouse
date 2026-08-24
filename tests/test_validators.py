import unittest

from scraper.network_parser import product_candidates
from scraper.validators import same_name, validate_currency, validate_region


class ValidationTests(unittest.TestCase):
    def test_names_are_strict(self):
        self.assertTrue(same_name("K2 Plus Combo", "Creality K2 Plus Combo 3D Printer"))
        self.assertFalse(same_name("H2S Laser Full Combo", "H2S AMS Combo"))

    def test_regions(self):
        self.assertIsNone(validate_region("https://store.creality.com/eu/products/x", "EU"))
        self.assertIsNotNone(validate_region("https://store.creality.com/eu/products/x", "US"))
        self.assertIsNone(validate_region("https://uk.store.bambulab.com/products/x", "UK"))

    def test_currency(self):
        self.assertIsNone(validate_currency("CA", "CAD"))
        self.assertIsNotNone(validate_currency("CA", "USD"))

    def test_price_candidates_not_arbitrary_numbers(self):
        data = [{"save": 200}, {"title": "Combo", "price": 999, "currency": "USD"}]
        self.assertEqual(product_candidates(data), [data[1]])


if __name__ == "__main__":
    unittest.main()

