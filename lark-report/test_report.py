"""Chạy: python3 -m unittest lark-report/test_report.py  (từ thư mục gốc repo)"""

import json
import os
import sys
import unittest
import urllib.parse
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import ads_card  # noqa: E402
import ads_sources  # noqa: E402
import send_report  # noqa: E402

HERE = os.path.dirname(__file__)


def _query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


class ReportRangeTest(unittest.TestCase):
    def test_daily(self):
        cur, prev = ads_sources.report_range("daily", date(2026, 11, 14))
        self.assertEqual(cur, (date(2026, 11, 13), date(2026, 11, 13)))
        self.assertEqual(prev, (date(2026, 11, 12), date(2026, 11, 12)))

    def test_weekly_is_previous_monday_to_sunday(self):
        for today in (date(2026, 11, 9), date(2026, 11, 14), date(2026, 11, 15)):
            cur, prev = ads_sources.report_range("weekly", today)
            self.assertEqual(cur, (date(2026, 11, 2), date(2026, 11, 8)))
            self.assertEqual(prev, (date(2026, 10, 26), date(2026, 11, 1)))

    def test_monthly_crosses_year(self):
        cur, prev = ads_sources.report_range("monthly", date(2026, 1, 1))
        self.assertEqual(cur, (date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(prev, (date(2025, 11, 1), date(2025, 11, 30)))


class TikTokFetchTest(unittest.TestCase):
    def test_batches_of_five_and_parses_metrics(self):
        ids = [str(i) for i in range(7)]
        calls = []

        def fake_get(url, headers=None):
            calls.append((url, headers))
            q = _query(url)
            if "/advertiser/info/" in url:
                return {"code": 0, "data": {"list": [{"advertiser_id": i, "name": f"KH {i}"}
                                                     for i in json.loads(q["advertiser_ids"])]}}
            batch = json.loads(q["advertiser_ids"])
            self.assertLessEqual(len(batch), 5)
            self.assertEqual(json.loads(q["dimensions"]), ["advertiser_id"])
            rows = [{"dimensions": {"advertiser_id": batch[0]},
                     "metrics": {"spend": "1500000", "impressions": "1000", "clicks": "10",
                                 "conversion": "5", "complete_payment": "0", "currency": "VND"}}]
            return {"code": 0, "data": {"list": rows}}

        env = {"TIKTOK_ADVERTISER_IDS": ",".join(ids)}
        with mock.patch.dict(os.environ, env), mock.patch.object(ads_sources, "_get_json", fake_get):
            accounts = ads_sources.fetch_tiktok("tok", date(2026, 11, 2), date(2026, 11, 8))

        report_calls = [c for c in calls if "/report/" in c[0]]
        self.assertEqual(len(report_calls), 2)
        self.assertEqual(report_calls[0][1], {"Access-Token": "tok"})
        self.assertEqual([a["name"] for a in accounts], ["KH 0", "KH 5"])
        self.assertEqual(accounts[0]["spend"], 1_500_000)
        self.assertEqual(accounts[0]["conversions"], 5)

    def test_api_error_is_raised(self):
        with mock.patch.dict(os.environ, {"TIKTOK_ADVERTISER_IDS": "1"}), \
                mock.patch.object(ads_sources, "_get_json",
                                  return_value={"code": 40105, "message": "Access token is incorrect"}):
            with self.assertRaisesRegex(RuntimeError, "40105"):
                ads_sources.fetch_tiktok("bad", date(2026, 11, 2), date(2026, 11, 8))


class MetaFetchTest(unittest.TestCase):
    def test_paging_filter_and_actions(self):
        page1 = {"data": [
            {"account_id": "1", "name": "KH A", "currency": "VND", "insights": {"data": [{
                "spend": "2000000", "impressions": "5000", "clicks": "50",
                "actions": [
                    {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "40"},
                    {"action_type": "lead", "value": "38"},
                    {"action_type": "link_click", "value": "50"},
                ]}]}},
            {"account_id": "2", "name": "Không chạy", "currency": "VND"},
        ], "paging": {"next": "https://graph.facebook.com/next-page"}}
        page2 = {"data": [{"account_id": "3", "name": "Không theo dõi", "currency": "VND",
                           "insights": {"data": [{"spend": "1"}]}}]}
        urls = []

        def fake_get(url, headers=None):
            urls.append(url)
            return page1 if len(urls) == 1 else page2

        with mock.patch.dict(os.environ, {"META_AD_ACCOUNT_IDS": "act_1,2"}), \
                mock.patch.object(ads_sources, "_get_json", fake_get):
            accounts = ads_sources.fetch_meta("tok", date(2026, 11, 2), date(2026, 11, 8))

        self.assertEqual(len(urls), 2)
        self.assertIn('"since": "2026-11-02"', _query(urls[0])["fields"])
        self.assertEqual(len(accounts), 1)
        a = accounts[0]
        self.assertEqual((a["messages"], a["leads"], a["purchases"]), (40, 38, 0))
        self.assertEqual(a["conversions"], 40)  # lấy loại lớn nhất, không cộng dồn

    def test_one_platform_failing_keeps_the_other(self):
        tiktok_rows = [{"platform": "TikTok", "spend": 1}]
        env = {"TIKTOK_ACCESS_TOKEN": "a", "META_ACCESS_TOKEN": "b"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(ads_sources, "fetch_tiktok", return_value=tiktok_rows), \
                mock.patch.object(ads_sources, "fetch_meta", side_effect=RuntimeError("token hết hạn")):
            result = ads_sources.fetch_all("daily", date(2026, 11, 14))
        self.assertEqual(result["current"], tiktok_rows)
        self.assertEqual(result["errors"], ["Meta: token hết hạn"])


class AdsCardTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "sample_ads.json"), encoding="utf-8") as f:
            self.ads = json.load(f)
        self.ads["range"] = (date(2026, 11, 2), date(2026, 11, 8))

    def test_alerts(self):
        _, alerts = ads_card.build_ads_elements(self.ads)
        text = "\n".join(alerts)
        self.assertIn("Áo dài 2 **ngừng chi tiêu**", text)
        self.assertIn("KENZA VIỆT NAM chi tiêu **giảm 58%**", text)
        self.assertNotIn("Cúc Phương", text)

    def test_foreign_currency_excluded_from_total(self):
        elements, _ = ads_card.build_ads_elements(self.ads)
        dump = json.dumps(elements, ensure_ascii=False)
        self.assertIn("Chưa cộng TK ngoại tệ: USD", dump)
        self.assertIn("**Tổng chi tiêu**\\n61 tr", dump)

    def test_all_sources_failed_shows_error_not_zero(self):
        ads = {"current": [], "previous": [], "range": self.ads["range"], "errors": ["TikTok: lỗi"]}
        elements, alerts = ads_card.build_ads_elements(ads)
        dump = json.dumps(elements, ensure_ascii=False)
        self.assertIn("Không lấy được số liệu", dump)
        self.assertNotIn("Tổng chi tiêu", dump)
        self.assertEqual(alerts, [])

    def test_card_without_sheet(self):
        card = send_report.build_card(None, "weekly", ads=self.ads)
        self.assertEqual(card["header"]["template"], "red")
        self.assertIn("TikTok/Meta Ads API", json.dumps(card, ensure_ascii=False))

    def test_card_with_sheet_and_ads(self):
        with open(os.path.join(HERE, "sample_kpi.csv"), encoding="utf-8") as f:
            data = send_report.parse_kpi_csv(f.read())
        card = send_report.build_card(data, "weekly", ads=self.ads)
        dump = json.dumps(card, ensure_ascii=False)
        self.assertIn("📊 Tổng quan", dump)
        self.assertIn("📣 Quảng cáo khách hàng", dump)


if __name__ == "__main__":
    unittest.main()
