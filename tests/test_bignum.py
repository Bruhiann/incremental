import math
import unittest

from seed.bignum import N, Num, ZERO, ONE, fmt, fmt_time


class TestConstruction(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual((Num(900).m, Num(900).e), (9.0, 2))
        self.assertEqual((Num(1).m, Num(1).e), (1.0, 0))
        self.assertEqual((Num(0.05).m, Num(0.05).e), (5.0, -2))
        self.assertEqual((Num(0).m, Num(0).e), (0.0, 0))

    def test_negative(self):
        n = Num(-1500)
        self.assertEqual((n.m, n.e), (-1.5, 3))
        self.assertTrue(n < 0)

    def test_huge_python_int(self):
        n = Num(10**400)
        self.assertEqual(n.e, 400)
        self.assertAlmostEqual(n.m, 1.0, places=9)

    def test_from_exp(self):
        n = Num.from_exp(37.5)
        self.assertEqual(n.e, 37)
        self.assertAlmostEqual(n.m, 10**0.5, places=9)

    def test_string_forms(self):
        self.assertEqual(Num("1.5e10").e, 10)
        self.assertEqual(Num("900").e, 2)
        self.assertEqual(Num("").m, 0.0)


class TestArithmetic(unittest.TestCase):
    def test_add_same_scale(self):
        self.assertAlmostEqual((Num(150) + Num(50)).to_float(), 200.0)

    def test_add_ignores_negligible(self):
        big = Num(1, 100)
        self.assertEqual(big + Num(1), big)

    def test_add_zero_identity(self):
        self.assertEqual(ZERO + Num(42), Num(42))
        self.assertEqual(Num(42) + 0, Num(42))

    def test_sub(self):
        self.assertAlmostEqual((Num(1000) - Num(1)).to_float(), 999.0)
        self.assertTrue((Num(5) - Num(9)) < 0)

    def test_mul_div(self):
        self.assertAlmostEqual((Num(2, 50) * Num(3, 50)).to_float() / 6e100, 1.0)
        q = Num(6, 100) / Num(3, 40)
        self.assertEqual(q.e, 60)
        self.assertAlmostEqual(q.m, 2.0, places=9)

    def test_div_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            Num(1) / ZERO

    def test_mul_by_zero(self):
        self.assertEqual(Num(5, 300) * ZERO, ZERO)

    def test_beyond_float64(self):
        """The whole point of Num: keep going past 1.8e308."""
        n = Num(1, 300) * Num(1, 300)
        self.assertEqual(n.e, 600)
        self.assertEqual(n.to_float(), math.inf)  # float degrades, Num does not
        self.assertTrue(n > Num(1, 599))

    def test_pow(self):
        self.assertAlmostEqual((Num(10) ** 3).to_float(), 1000.0, places=6)
        big = Num(1, 1000) ** 5
        self.assertEqual(big.e, 5000)

    def test_pow_edges(self):
        self.assertEqual(Num(123) ** 0, ONE)
        self.assertEqual(Num(123) ** 1, Num(123))
        self.assertEqual(ZERO ** 2, ZERO)

    def test_sqrt(self):
        self.assertAlmostEqual(Num(144).sqrt().to_float(), 12.0, places=6)

    def test_repeated_ops_stay_normalized(self):
        n = Num(1)
        for _ in range(500):
            n = n * Num(3) + Num(7)
        self.assertTrue(1.0 <= abs(n.m) < 10.0)

    def test_growth_curve_precision(self):
        """cost = base * growth**n must stay sane at large n."""
        cost = Num(15) * (Num(1.11) ** 500)
        self.assertAlmostEqual(cost.log10(), math.log10(15) + 500 * math.log10(1.11), places=6)


class TestComparison(unittest.TestCase):
    def test_ordering(self):
        self.assertTrue(Num(1, 50) > Num(9, 49))
        self.assertTrue(Num(-5) < Num(1))
        self.assertTrue(Num(-1, 50) < Num(-1, 49))
        self.assertTrue(ZERO < Num(1))
        self.assertTrue(Num(-1) < ZERO)

    def test_equality_and_coercion(self):
        self.assertEqual(Num(1000), 1000)
        self.assertNotEqual(Num(1000), None)
        self.assertTrue(Num(5) >= 5)

    def test_clamp_and_minmax(self):
        self.assertEqual(Num(-5).clamp_min(0), ZERO)
        self.assertEqual(Num(5).clamp_min(0), Num(5))
        self.assertEqual(Num(3).max(Num(9)), Num(9))
        self.assertEqual(Num(3).min(Num(9)), Num(3))

    def test_bool(self):
        self.assertFalse(bool(ZERO))
        self.assertTrue(bool(Num(1, -50)))


class TestFormatting(unittest.TestCase):
    def test_ladder(self):
        cases = {
            0: "0",
            5: "5.00",
            15.6: "15.6",
            999: "999",
            1240: "1.24K",
            15_600_000: "15.6M",
            8.42e9: "8.42B",
            2.11e12: "2.11T",
            7.84e15: "7.84Qa",
        }
        for value, expected in cases.items():
            self.assertEqual(fmt(value), expected, f"fmt({value})")

    def test_scientific_takeover(self):
        self.assertEqual(fmt(Num(1.42, 37)), "1.42e37")
        self.assertTrue(fmt(Num(1, 35)).endswith("Dc"))

    def test_nested_exponent(self):
        s = fmt(Num(1.42, 2_000_000))
        self.assertTrue(s.startswith("1.42e"))
        self.assertIn("M", s)  # exponent itself formatted: 1.42e2.00M

    def test_small_and_negative(self):
        self.assertEqual(fmt(0.5), "0.5")
        self.assertTrue(fmt(-1240).startswith("-1.24K"))
        self.assertIn("e-", fmt(Num(1, -9)))

    def test_time(self):
        self.assertEqual(fmt_time(45), "45s")
        self.assertEqual(fmt_time(750), "12m 30s")
        self.assertEqual(fmt_time(11100), "3h 05m")
        self.assertEqual(fmt_time(float("inf")), "never")


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        for original in (ZERO, Num(1), Num(1.2345, 678), Num(-9.9, 42), Num(5, -30)):
            restored = Num.from_json(original.to_json())
            self.assertEqual(restored.e, original.e)
            self.assertAlmostEqual(restored.m, original.m, places=12)

    def test_from_json_tolerates_raw(self):
        self.assertEqual(Num.from_json(1000), Num(1000))
        self.assertEqual(Num.from_json(None), ZERO)

    def test_json_is_a_plain_string(self):
        self.assertIsInstance(Num(1, 500).to_json(), str)


class TestConversion(unittest.TestCase):
    def test_to_int(self):
        self.assertEqual(Num(12345).to_int(), 12345)
        self.assertEqual(Num(1, 30).to_int(), 10**30)
        self.assertEqual(ZERO.to_int(), 0)

    def test_log10(self):
        self.assertAlmostEqual(Num(1, 100).log10(), 100.0, places=9)
        self.assertEqual(ZERO.log10(), -math.inf)


if __name__ == "__main__":
    unittest.main()
