from __future__ import annotations

import unittest

import pandas as pd

from salary_pipeline.ops.lookup import if_ladder, lookup_match_index, sumifs_by_keys


class TestLookupOps(unittest.TestCase):
    def test_lookup_match_index(self) -> None:
        table = pd.DataFrame({"key": ["唐鹏", "赵思梵"], "value": [0.8, 1.0]})
        result = lookup_match_index(
            pd.Series(["唐鹏", "不存在"]),
            table["key"],
            table["value"],
        )
        self.assertAlmostEqual(result.iloc[0], 0.8)
        self.assertAlmostEqual(result.iloc[1], 0.0)

    def test_sumifs_by_keys(self) -> None:
        frame = pd.DataFrame(
            {
                "P": ["唐鹏", "唐鹏", "其他"],
                "K": [100, 200, 50],
                "AB": [1, 0, 10],
            }
        )
        total = sumifs_by_keys(
            frame,
            "K",
            [("AB", lambda s: s > 0), ("P", "唐鹏")],
        )
        self.assertEqual(total, 100.0)

    def test_if_ladder(self) -> None:
        x = pd.Series([0.5, 0.9, 1.1])
        out = if_ladder(
            [x < 0.85, x < 1.0],
            [0.0, x * 0.015],
            default=0.018,
        )
        self.assertAlmostEqual(out.iloc[0], 0.0)
        self.assertAlmostEqual(out.iloc[1], 0.9 * 0.015)
        self.assertAlmostEqual(out.iloc[2], 0.018)


if __name__ == "__main__":
    unittest.main()
