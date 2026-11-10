"""Test logic thuần của market_archive.py (gộp ngày, null, công thức premium).

Chạy: python3 -m unittest tests/test_market_archive.py -v
Script nằm ngoài repo: ~/.hermes/profiles/coder/scripts/market_archive.py
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.expanduser("~/.hermes/profiles/coder/scripts"))
import market_archive as ma  # noqa: E402

API = {
    "p2p": {"buy": 25824, "sell": 25807, "mid": 25816, "updatedAt": "2026-11-10T02:39:16Z"},
    "vcb": {"cashBuy": 25350, "transferBuy": 25380, "sell": 25760, "updatedAt": "2026-11-10T01:37:16Z"},
    "gold": {"sjcBuy": 138500000, "sjcSell": 141500000, "ringBuy": 137200000, "ringSell": 141200000,
             "xauUsd": 4128.4, "delayed": False, "updatedAt": "2026-11-10T02:30:04Z"},
}


def at(h, m=7, day=10):
    return datetime(2026, 11, day, h, m, tzinfo=ma.VN_TZ)


class BuildSample(unittest.TestCase):
    def test_full(self):
        s = ma.build_sample(API, at(10))
        self.assertEqual(s["t"], "2026-11-10T03:07:00+00:00")
        self.assertEqual((s["usdt_mid"], s["vcb_sell"], s["sjc_sell"], s["ring_buy"], s["xau_usd"]),
                         (25816, 25760, 141500000, 137200000, 4128.4))
        self.assertIs(s["delayed"], False)

    def test_delayed_gold_is_null_not_carried(self):
        api = {**API, "gold": {**API["gold"], "delayed": True}}
        s = ma.build_sample(api, at(10))
        for k in ("sjc_buy", "sjc_sell", "ring_buy", "ring_sell", "xau_usd"):
            self.assertIsNone(s[k])
        self.assertIs(s["delayed"], True)
        self.assertEqual(s["vcb_sell"], 25760)

    def test_failed_source_and_garbage_are_null(self):
        api = {"p2p": None, "vcb": {"sell": "abc", "cashBuy": -5}, "gold": {"xauUsd": 0, "sjcSell": 141500000}}
        s = ma.build_sample(api, at(10))
        self.assertIsNone(s["usdt_mid"])
        self.assertIsNone(s["vcb_sell"])
        self.assertIsNone(s["vcb_cash_buy"])
        self.assertIsNone(s["xau_usd"])
        self.assertEqual(s["sjc_sell"], 141500000)

    def test_nothing_valid_returns_none(self):
        self.assertIsNone(ma.build_sample({}, at(10)))
        self.assertIsNone(ma.build_sample({"p2p": {}, "vcb": {}, "gold": {}}, at(10)))


class Derive(unittest.TestCase):
    def test_formulas(self):
        v = ma.sample_values(ma.build_sample(API, at(10)))
        self.assertEqual(v["usdt_spread"], 17)
        self.assertAlmostEqual(v["usdt_vs_vcb_pct"], (25816 - 25760) / 25760 * 100, places=3)
        world = 4128.4 * 1.20565 * 25760
        self.assertAlmostEqual(v["sjc_vs_world_mil"], (141500000 - world) / 1e6, places=2)
        self.assertAlmostEqual(v["sjc_vs_world_pct"], (141500000 - world) / world * 100, places=3)
        self.assertAlmostEqual(v["sjc_spread_pct"], 3 / 141.5 * 100, places=3)
        self.assertAlmostEqual(v["ring_spread_pct"], 4 / 141.2 * 100, places=3)
        self.assertAlmostEqual(v["usd_cash_spread_pct"], 410 / 25760 * 100, places=3)

    def test_world_premium_known_value(self):
        # 2.000 USD/oz, 25.000 VND/USD -> 2000*1.20565*25000 = 60.2825 triệu/lượng
        d = ma.derive({"xau_usd": 2000, "vcb_sell": 25000, "sjc_sell": 70_282_500})
        self.assertAlmostEqual(d["sjc_vs_world_mil"], 10.0, places=3)
        self.assertAlmostEqual(d["sjc_vs_world_pct"], 10 / 60.2825 * 100, places=3)

    def test_missing_input_gives_none(self):
        d = ma.derive({"vcb_sell": 25000, "sjc_sell": 140e6, "sjc_buy": 137e6})  # thiếu xau
        self.assertIsNone(d["sjc_vs_world_mil"])
        self.assertIsNone(d["sjc_vs_world_pct"])
        self.assertIsNone(d["usdt_vs_vcb_pct"])
        self.assertIsNotNone(d["sjc_spread_pct"])


class Aggregate(unittest.TestCase):
    def test_ohlc_and_null_handling(self):
        s1 = ma.build_sample(API, at(9))
        api2 = {**API, "vcb": {**API["vcb"], "sell": 25800}, "gold": {**API["gold"], "delayed": True}}
        s2 = ma.build_sample(api2, at(10))
        api3 = {**API, "p2p": {"buy": 25900, "sell": 25880, "mid": 25890}, "vcb": {**API["vcb"], "sell": 25790}}
        s3 = ma.build_sample(api3, at(11))
        row = ma.aggregate_day("2026-11-10", [s3, s1, s2])  # xáo thứ tự: phải tự sắp theo t
        v = row["vcb_sell"]
        self.assertEqual((v["open"], v["high"], v["low"], v["close"], v["n"]), (25760, 25800, 25760, 25790, 3))
        sj = row["sjc_sell"]  # s2 delayed -> null, không tính vào n, không carry
        self.assertEqual((sj["open"], sj["close"], sj["n"]), (141500000, 141500000, 2))
        self.assertEqual(row["usdt_mid"]["n"], 3)
        self.assertEqual(row["usdt_mid"]["close"], 25890)
        self.assertEqual(row["sjc_vs_world_pct"]["n"], 2)
        self.assertEqual(row["samples"], 3)
        self.assertNotIn("spread_unreliable", row)

    def test_all_null_metric_is_none(self):
        s = ma.build_sample({"vcb": API["vcb"]}, at(9))
        row = ma.aggregate_day("2026-11-10", [s])
        self.assertIsNone(row["sjc_sell"])
        self.assertIsNone(row["xau_usd"])
        self.assertIsNone(row["sjc_vs_world_pct"])
        self.assertEqual(row["vcb_sell"]["n"], 1)

    def test_vn_day_boundary(self):
        late = ma.build_sample(API, datetime(2026, 11, 9, 23, 30, tzinfo=ma.VN_TZ))  # = 16:30 UTC
        early = ma.build_sample(API, datetime(2026, 11, 10, 0, 7, tzinfo=ma.VN_TZ))  # = 17:07 UTC ngày 9
        self.assertEqual(ma.vn_day(late["t"]), "2026-11-09")
        self.assertEqual(ma.vn_day(early["t"]), "2026-11-10")

    def test_old_day_flags_spread_unreliable(self):
        row = ma.aggregate_day("2026-11-09", [ma.build_sample(API, at(9, day=9))])
        self.assertTrue(row["spread_unreliable"])


class ApplySample(unittest.TestCase):
    def test_gap_guard_and_trim_and_backfill_kept(self):
        now = at(10)
        backfill = {"d": "2026-08-09", "backfill": True, "samples": 1}
        daily = ma.new_daily([backfill], "x")
        hourly = {"points": [dict(ma.build_sample(API, now - timedelta(days=60)))]}  # quá 45 ngày
        h, d, added = ma.apply_sample(hourly, daily, ma.build_sample(API, now), now)
        self.assertTrue(added)
        self.assertEqual(len(h["points"]), 1)  # điểm 60 ngày trước bị cắt
        self.assertEqual([r["d"] for r in d["days"]], ["2026-08-09", "2026-11-10"])
        self.assertTrue(d["days"][0]["backfill"])  # dòng backfill còn nguyên
        self.assertEqual(d["schema_version"], 2)
        self.assertIn("usdt_vs_vcb_pct", d["method"])
        # mẫu thứ 2 cách 10 phút -> bị chặn
        h2, d2, added2 = ma.apply_sample(h, d, ma.build_sample(API, now + timedelta(minutes=10)), now)
        self.assertFalse(added2)
        self.assertEqual(len(h2["points"]), 1)

    def test_window_edge_day_not_overwritten(self):
        now = at(10)
        edge = now - timedelta(days=ma.KEEP_DAYS) + timedelta(hours=2)  # ngày đầu cửa sổ, bị cắt dở
        kept = {"d": edge.astimezone(ma.VN_TZ).date().isoformat(), "backfill": False, "marker": "giữ"}
        h, d, _ = ma.apply_sample({"points": [ma.build_sample(API, edge)]}, ma.new_daily([kept], "x"),
                                  ma.build_sample(API, now), now)
        self.assertEqual(d["days"][0].get("marker"), "giữ")


BRANDS = [
    {"id": "btmh_sjc", "buy": 138500000, "sell": 141500000},
    {"id": "btmh_kgb", "buy": 137000000, "sell": 141000000},
    {"id": "pnj_ring", "buy": 136700000, "sell": 140900000},
    {"id": "sjc_sjc", "buy": 138500000, "sell": 141500000},  # đã có sjc_* nên không lưu lại
    {"id": "doji_ring", "buy": 137200000, "sell": 1},  # sell rác => null, không phải 1 đ
]


class Brands(unittest.TestCase):
    def test_sample_has_brand_prices_and_ignores_unknown_or_garbage(self):
        s = ma.build_sample({**API, "brands": BRANDS}, at(10))
        self.assertEqual((s["btmh_kgb_buy"], s["btmh_kgb_sell"]), (137000000, 141000000))
        self.assertEqual(s["pnj_ring_sell"], 140900000)
        self.assertIsNone(s["doji_ring_sell"])
        self.assertIsNone(s["pq_ring_buy"])  # hãng không có trong API => null
        self.assertNotIn("sjc_sjc_buy", s)

    def test_sample_without_brands_key_is_all_null(self):
        s = ma.build_sample(API, at(10))
        for b in ma.BRAND_IDS:
            self.assertIsNone(s[f"{b}_buy"])
            self.assertIsNone(s[f"{b}_sell"])

    def test_spread_formula_and_missing_side(self):
        v = ma.sample_values(ma.build_sample({**API, "brands": BRANDS}, at(10)))
        self.assertAlmostEqual(v["btmh_kgb_spread_pct"], 4 / 141 * 100, places=3)
        self.assertAlmostEqual(v["pnj_ring_spread_pct"], 4.2 / 140.9 * 100, places=3)
        self.assertIsNone(v["doji_ring_spread_pct"])  # thiếu bán ra
        self.assertIsNone(v["pq_sjc_spread_pct"])

    def test_day_aggregate_and_old_rows_normalized(self):
        s1 = ma.build_sample({**API, "brands": BRANDS}, at(9))
        s2 = ma.build_sample({**API, "brands": [{"id": "btmh_kgb", "buy": 137200000, "sell": 141000000}]}, at(10))
        row = ma.aggregate_day("2026-11-10", [s1, s2])
        k = row["btmh_kgb_buy"]
        self.assertEqual((k["open"], k["close"], k["n"]), (137000000, 137200000, 2))
        self.assertEqual(row["pnj_ring_sell"]["n"], 1)
        self.assertIsNone(row["pq_ring_buy"])
        old = ma.normalize_row({"d": "2026-08-09", "backfill": True})
        self.assertTrue(all(m in old and old[m] is None for m in ma.ALL_METRICS))
        self.assertIn("btmh_kgb_spread_pct", ma.METHOD)
        _, d, _ = ma.apply_sample({"points": []}, ma.new_daily([{"d": "2026-08-09", "backfill": True}], "x"), s1, at(10))
        self.assertIn("pnj_ring_buy", d["days"][0])  # dòng backfill cũ được thêm cột null


if __name__ == "__main__":
    unittest.main()
