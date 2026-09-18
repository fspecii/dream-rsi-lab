import unittest
from fulfilment.rates import shipping_cents
from fulfilment.checkout import total_cents


class ShippingTests(unittest.TestCase):
    def test_started_kilograms(self):
        for grams, expected in [(0, 0), (1, 300), (999, 300), (1000, 300), (1001, 600), (2500, 900)]:
            with self.subTest(grams=grams):
                self.assertEqual(shipping_cents(grams), expected)

    def test_negative_weight(self):
        with self.assertRaises(ValueError):
            shipping_cents(-1)


class CheckoutTests(unittest.TestCase):
    def test_empty_cart(self):
        self.assertEqual(total_cents([]), 0)

    def test_quantity_affects_shipping(self):
        self.assertEqual(total_cents([{'unit_cents': 1000, 'quantity': 3, 'unit_grams': 400}]), 3600)

    def test_discount_excludes_shipping(self):
        self.assertEqual(total_cents([{'unit_cents': 1000, 'quantity': 1, 'unit_grams': 1000}], 20), 1100)

    def test_discount_rounds_down_before_shipping(self):
        self.assertEqual(total_cents([{'unit_cents': 999, 'quantity': 1, 'unit_grams': 500}], 15), 1149)

    def test_multiple_items(self):
        items = [{'unit_cents': 900, 'quantity': 2, 'unit_grams': 200},
                 {'unit_cents': 300, 'quantity': 1, 'unit_grams': 800}]
        self.assertEqual(total_cents(items, 10), 2490)
