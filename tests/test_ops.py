from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.ops.basic import ratio_with_cap, sumif_by_key


class TestSumifByKey(unittest.TestCase):
    def setUp(self) -> None:
        self.source = pd.DataFrame(
            {
                "姓名": ["唐鹏", "唐鹏", "赵思梵", "姓名"],
                "考核量": [2, 3, 9, 0],
            }
        )

    def test_scalar_criteria(self) -> None:
        self.assertEqual(sumif_by_key(self.source, "姓名", "考核量", "唐鹏"), 5.0)
        self.assertEqual(sumif_by_key(self.source, "姓名", "考核量", "赵思梵"), 9.0)
        self.assertEqual(sumif_by_key(self.source, "姓名", "考核量", "不存在"), 0.0)

    def test_series_criteria(self) -> None:
        result = sumif_by_key(
            self.source,
            "姓名",
            "考核量",
            pd.Series(["唐鹏", "赵思梵"]),
        )
        self.assertEqual(list(result), [5.0, 9.0])


class TestRatioWithCap(unittest.TestCase):
    def test_zero_denominator(self) -> None:
        self.assertEqual(ratio_with_cap(3, 0, cap=1.2), 0.0)

    def test_cap_applied(self) -> None:
        self.assertAlmostEqual(ratio_with_cap(6, 5, cap=1.2), 1.2)
        self.assertAlmostEqual(ratio_with_cap(3, 5, cap=1.2), 0.6)

    def test_series(self) -> None:
        out = ratio_with_cap(pd.Series([6, 0]), pd.Series([5, 5]), cap=1.2)
        self.assertAlmostEqual(out.iloc[0], 1.2)
        self.assertAlmostEqual(out.iloc[1], 0.0)


if __name__ == "__main__":
    unittest.main()
