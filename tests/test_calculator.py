import unittest

from dragcalculator.calculator import (
    CalculationError,
    calculate_expression,
    calculate_from_edited_numbers,
    calculate_from_text,
    calculate_with_operator,
)


class CalculatorTests(unittest.TestCase):
    def test_sums_plain_numbers(self):
        result = calculate_from_text("120 30 5")
        self.assertEqual(result.mode, "sum")
        self.assertEqual(result.display, "155")

    def test_evaluates_expression(self):
        result = calculate_from_text("120 + 30 * 5")
        self.assertEqual(result.mode, "expression")
        self.assertEqual(result.display, "270")

    def test_removes_thousands_commas(self):
        result = calculate_from_text("1,200 + 300")
        self.assertEqual(result.display, "1500")

    def test_supports_unicode_operators(self):
        result = calculate_from_text("12 × 3 ÷ 2")
        self.assertEqual(result.display, "18")

    def test_falls_back_to_sum_for_common_plus_ocr_noise(self):
        result = calculate_from_text("120 -\n+30")
        self.assertEqual(result.mode, "sum")
        self.assertEqual(result.display, "150")

    def test_recalculates_sum_from_edited_numbers(self):
        base = calculate_from_text("120 30")
        result = calculate_from_edited_numbers(base, ["120", "35"])
        self.assertEqual(result.expression, "120+35")
        self.assertEqual(result.display, "155")

    def test_recalculates_expression_from_edited_numbers(self):
        base = calculate_from_text("120 + 30 * 5")
        result = calculate_from_edited_numbers(base, ["120", "40", "5"])
        self.assertEqual(result.expression, "120+40*5")
        self.assertEqual(result.display, "320")

    def test_calculates_grouped_custom_expression(self):
        result = calculate_expression("3 + (4 + 5)")
        self.assertEqual(result.display, "12")

    def test_calculates_scientific_functions(self):
        result = calculate_expression("sqrt(9) + sin(pi / 2) + 2^3")
        self.assertEqual(result.display, "12")

    def test_calculates_uniform_operation(self):
        result = calculate_with_operator(["20", "4", "2"], "/")
        self.assertEqual(result.expression, "20/4/2")
        self.assertEqual(result.display, "2.5")

    def test_raises_when_no_numbers_found(self):
        with self.assertRaises(CalculationError):
            calculate_from_text("hello")


if __name__ == "__main__":
    unittest.main()
